"""Gemini client (TRD §8.1): token bucket + concurrency cap, 429 backoff honouring Retry-After,
memoization in llm_cache, and replay mode for tests.

Memoization is the restart story: a job re-run after a Render restart replays finished calls
from Postgres for free. Keys are sha256(model | prompt_version | schema_hash | input).

Never log prompts or responses (TRD §12). Log only keys' prefixes, timings and codes.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlmodel import Session

from app.config import Settings, get_settings
from app.db import get_engine
from app.errors import ConanError
from app.models import LLMCache

log = logging.getLogger("conan.gemini")

REPLAY_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "llm"
BACKOFF_S = (2.0, 4.0, 8.0)


class LLMRateLimited(Exception):
    def __init__(self, retry_after: float | None = None, daily: bool = False):
        super().__init__(f"rate limited (retry_after={retry_after}, daily={daily})")
        self.retry_after, self.daily = retry_after, daily


class LLMUnavailable(Exception):
    pass


class ModelNotFound(Exception):
    pass


@dataclass
class RawResponse:
    text: str
    finish_reason: str | None
    model: str | None = None  # which model in the chain actually answered


@dataclass
class LLMResult:
    data: dict | None  # parsed JSON, or None if the model returned non-JSON
    text: str
    finish_reason: str | None
    cached: bool
    key: str
    model: str | None = None

    @property
    def truncated(self) -> bool:
        return (self.finish_reason or "").upper() == "MAX_TOKENS"


# (system, user, schema_model, api_key, model) -> RawResponse
Transport = Callable[[str, str, type[BaseModel], str, str], Awaitable[RawResponse]]
PRIMARY_RETRY_S = 300  # after falling back, try the primary model again this often
Clock = Callable[[], float]


class TokenBucket:
    def __init__(self, rpm: int, capacity: int, clock: Clock = time.monotonic):
        self.rate = max(rpm, 1) / 60.0
        self.capacity = float(max(1, capacity))
        self.tokens = self.capacity
        self._clock = clock
        self.updated = clock()
        self._lock = asyncio.Lock()

    def refill(self, now: float) -> None:
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now

    def has_token(self) -> bool:
        return self.tokens >= 1 - 1e-9  # float refills can land a hair under 1.0

    def wait_time(self) -> float:
        # >= 1 ms: a sub-resolution wait would never advance the clock and would spin
        return 0.0 if self.has_token() else max((1 - self.tokens) / self.rate, 0.001)

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                self.refill(self._clock())
                if self.has_token():
                    self.tokens = max(0.0, self.tokens - 1)
                    return
                await asyncio.sleep(self.wait_time())


class AllKeysExhausted(Exception):
    pass


@dataclass
class KeyState:
    index: int  # 1-based, for logs; the key itself is never logged
    key: str
    bucket: TokenBucket
    cooldown_until: float = 0.0  # per-minute 429: skip this key until then
    exhausted_until: float = 0.0  # daily quota: skip until Gemini's reset (midnight Pacific)
    calls: int = 0


def seconds_until_quota_reset(now: dt.datetime | None = None) -> float:
    """Gemini free-tier daily quotas reset at midnight Pacific time."""
    pt = ZoneInfo("America/Los_Angeles")
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(pt)
    nxt = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (nxt - now).total_seconds() + 60  # a minute of slack


class KeyPool:
    """Several API keys used together: each has its own RPM bucket, so throughput scales with the
    number of keys. A per-minute 429 cools one key down and the call moves to the next key; a daily
    quota parks the key until reset. Only when every key is out does the caller get LLM_QUOTA."""

    def __init__(self, keys: list[str], rpm: int, capacity: int, clock: Clock = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self._clock, self._sleep = clock, sleep
        self.keys = [KeyState(i, k, TokenBucket(rpm, capacity, clock)) for i, k in enumerate(keys, start=1)]
        self._lock = asyncio.Lock()

    def available(self) -> int:
        now = self._clock()
        return sum(k.exhausted_until <= now for k in self.keys)

    async def acquire(self) -> KeyState:
        async with self._lock:
            while True:
                now = self._clock()
                live = [k for k in self.keys if k.exhausted_until <= now]
                if not live:
                    raise AllKeysExhausted()
                for k in live:
                    k.bucket.refill(now)
                ready = [k for k in live if k.cooldown_until <= now and k.bucket.has_token()]
                if ready:
                    k = max(ready, key=lambda k: (k.bucket.tokens, -k.calls))  # spread load across keys
                    k.bucket.tokens = max(0.0, k.bucket.tokens - 1)
                    k.calls += 1
                    return k
                await self._sleep(max(0.001, min(max(k.cooldown_until - now, k.bucket.wait_time()) for k in live)))

    def cool_down(self, k: KeyState, seconds: float) -> None:
        k.cooldown_until = max(k.cooldown_until, self._clock() + seconds)

    def exhaust(self, k: KeyState) -> None:
        k.exhausted_until = self._clock() + seconds_until_quota_reset()


def schema_hash(model: type[BaseModel]) -> str:
    return hashlib.sha256(json.dumps(model.model_json_schema(), sort_keys=True).encode()).hexdigest()[:16]


def cache_key(model_id: str, prompt_version: str, schema: type[BaseModel], system: str, user: str) -> str:
    h = hashlib.sha256()
    for part in (model_id, prompt_version, schema_hash(schema), system, user):
        h.update(part.encode())
        h.update(b"\x1f")
    return h.hexdigest()


def _parse(text: str) -> dict | None:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", text or "", re.S)  # tolerate stray prose around the JSON
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


class GeminiClient:
    def __init__(self, settings: Settings | None = None, transport: Transport | None = None,
                 use_db_cache: bool = True, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 clock: Clock = time.monotonic):
        self.s = settings or get_settings()
        # No key configured still gets one (empty) slot, so injected test transports work;
        # the real transport refuses an empty key.
        keys = self.s.api_keys or [""]
        self.pool = KeyPool(keys, self.s.gemini_rpm, capacity=min(self.s.gemini_concurrency, self.s.gemini_rpm),
                            clock=clock, sleep=sleep)
        self.sem = asyncio.Semaphore(self.s.gemini_concurrency)
        self.use_db_cache = use_db_cache
        self._sleep = sleep
        self._transport = transport
        self._clock = clock
        self._genai: dict[str, object] = {}
        self.models = self.s.models
        self._dead_models: set[str] = set()  # 404: retired / mistyped, skipped for this process
        self._preferred: str | None = None  # model that last answered (sticky); None = start at the primary
        self._preferred_since = clock()
        self.hits = self.misses = 0

    # ------------------------------------------------------------ public

    async def generate(self, system: str, user: str, schema: type[BaseModel]) -> LLMResult:
        # The whole model chain is part of the key: changing GEMINI_MODEL or the fallbacks re-runs calls.
        key = cache_key("|".join(self.models), self.s.prompt_version, schema, system, user)

        if self.s.llm_mode == "replay":
            raw = self._replay_load(key)
            self.hits += 1
            return LLMResult(_parse(raw.text), raw.text, raw.finish_reason, True, key, raw.model)

        if self.use_db_cache and (hit := await asyncio.to_thread(self._cache_get, key)):
            self.hits += 1
            return LLMResult(_parse(hit.text), hit.text, hit.finish_reason, True, key, hit.model)

        self.misses += 1
        raw = await self._call_with_retries(system, user, schema, key)
        if self.use_db_cache:
            await asyncio.to_thread(self._cache_put, key, raw)
        if self.s.llm_record:
            self._replay_save(key, raw)
        return LLMResult(_parse(raw.text), raw.text, raw.finish_reason, False, key, raw.model)

    # ------------------------------------------------------------ calling

    async def _call_with_retries(self, system: str, user: str, schema: type[BaseModel], key: str) -> RawResponse:
        transport = self._transport or self._genai_transport
        rate_retries = len(BACKOFF_S) + len(self.pool.keys) - 1  # one extra try per spare key
        rate_hits = transient = failed_this_round = 0
        if self._preferred and self._clock() - self._preferred_since > PRIMARY_RETRY_S:
            self._preferred = None  # give the primary model another chance
        start, hops = self._preferred, 0
        while True:
            live = [m for m in self.models if m not in self._dead_models]
            if not live:
                raise ConanError("LLM_UNAVAILABLE", "no usable model: check GEMINI_MODEL / GEMINI_FALLBACK_MODELS")
            base = live.index(start) if start in live else 0
            model = live[(base + hops) % len(live)]
            try:
                k = await self.pool.acquire()
            except AllKeysExhausted as exc:
                log.warning("llm all %d key(s) out of daily quota key=%s", len(self.pool.keys), key[:10])
                raise ConanError("LLM_QUOTA") from exc
            t0 = time.monotonic()
            try:
                async with self.sem:
                    raw = await asyncio.wait_for(transport(system, user, schema, k.key, model),
                                                 timeout=self.s.gemini_timeout_s)
                raw.model = model
                if model != (self._preferred or self.models[0]):
                    self._preferred, self._preferred_since = model, self._clock()
                log.info("llm call ok key=%s api_key=#%d model=%s ms=%d finish=%s", key[:10], k.index, model,
                         (time.monotonic() - t0) * 1000, raw.finish_reason)
                return raw
            except ModelNotFound:
                log.error("gemini model %r not found (retired or mistyped); dropping it", model)
                self._dead_models.add(model)
                continue
            except LLMRateLimited as exc:
                if exc.daily:
                    log.warning("llm api_key=#%d daily quota exhausted; failing over", k.index)
                    self.pool.exhaust(k)
                    continue
                if rate_hits >= rate_retries:
                    raise ConanError("LLM_QUOTA") from exc
                wait = max(BACKOFF_S[min(rate_hits, len(BACKOFF_S) - 1)], exc.retry_after or 0)
                rate_hits += 1
                log.warning("llm 429 api_key=#%d attempt=%d cool=%.1fs", k.index, rate_hits, wait)
                self.pool.cool_down(k, wait)  # the next acquire picks another key if one is free
            except (LLMUnavailable, asyncio.TimeoutError) as exc:
                # Overloaded (503) or slow: move to the next model at once; back off only after a full round.
                log.warning("llm unavailable model=%s api_key=#%d err=%s", model, k.index, type(exc).__name__)
                hops += 1
                failed_this_round += 1
                if failed_this_round >= len(live):
                    if transient >= len(BACKOFF_S):
                        raise ConanError("LLM_UNAVAILABLE") from exc
                    await self._sleep(BACKOFF_S[transient])
                    transient += 1
                    failed_this_round = 0

    async def _genai_transport(self, system: str, user: str, schema: type[BaseModel], api_key: str,
                               model: str) -> RawResponse:
        from google import genai
        from google.genai import errors, types

        if not api_key:
            raise ConanError("LLM_UNAVAILABLE", "GEMINI_API_KEY / GEMINI_API_KEYS not set")
        if api_key not in self._genai:
            self._genai[api_key] = genai.Client(api_key=api_key)
        client = self._genai[api_key]
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            response_mime_type="application/json",
            response_schema=schema,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),  # no tools, ever
            http_options=types.HttpOptions(timeout=int(self.s.gemini_timeout_s * 1000)),
        )
        try:
            resp = await client.aio.models.generate_content(model=model, contents=user, config=config)
        except errors.APIError as exc:
            if exc.code == 429:
                raise _rate_limit_from(exc) from exc
            if exc.code in (500, 502, 503, 504):
                raise LLMUnavailable(str(exc.code)) from exc
            if exc.code == 404:  # retired or mistyped model id: skip it, don't retry it
                raise ModelNotFound(model) from exc
            raise  # 400s are bugs in our request: surface them loudly
        finish = None
        if resp.candidates:
            fr = resp.candidates[0].finish_reason
            finish = getattr(fr, "name", None) or (str(fr) if fr else None)
        return RawResponse(text=resp.text or "", finish_reason=finish)

    # ------------------------------------------------------------ cache + replay

    def _cache_get(self, key: str) -> RawResponse | None:
        with Session(get_engine()) as s:
            row = s.get(LLMCache, key)
            return RawResponse(**row.response) if row else None

    def _cache_put(self, key: str, raw: RawResponse) -> None:
        with Session(get_engine()) as s:
            if s.get(LLMCache, key) is None:
                s.add(LLMCache(key=key, response={"text": raw.text, "finish_reason": raw.finish_reason,
                                                  "model": raw.model}))
                s.commit()

    def _replay_load(self, key: str) -> RawResponse:
        path = REPLAY_DIR / f"{key}.json"
        if not path.exists():
            raise ConanError("LLM_UNAVAILABLE", f"no replay recording for {key[:10]}")
        return RawResponse(**json.loads(path.read_text(encoding="utf-8")))

    def _replay_save(self, key: str, raw: RawResponse) -> None:
        REPLAY_DIR.mkdir(parents=True, exist_ok=True)
        (REPLAY_DIR / f"{key}.json").write_text(
            json.dumps({"text": raw.text, "finish_reason": raw.finish_reason, "model": raw.model}, ensure_ascii=False),
            encoding="utf-8")


def _rate_limit_from(exc) -> LLMRateLimited:
    """Read RetryInfo.retryDelay and whether the violated quota is per-day from a 429 body."""
    body = getattr(exc, "details", None) or getattr(exc, "response_json", None) or {}
    blob = json.dumps(body) if not isinstance(body, str) else body
    retry = None
    if m := re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', blob):
        retry = float(m.group(1))
    daily = bool(re.search(r"PerDay", blob))
    return LLMRateLimited(retry_after=retry, daily=daily)
