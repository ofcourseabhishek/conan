"""Gemini client (TRD §8.1): token bucket + concurrency cap, 429 backoff honouring Retry-After,
memoization in llm_cache, and replay mode for tests.

Memoization is the restart story: a job re-run after a Render restart replays finished calls
from Postgres for free. Keys are sha256(model | prompt_version | schema_hash | input).

Never log prompts or responses (TRD §12). Log only keys' prefixes, timings and codes.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

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


@dataclass
class RawResponse:
    text: str
    finish_reason: str | None


@dataclass
class LLMResult:
    data: dict | None  # parsed JSON, or None if the model returned non-JSON
    text: str
    finish_reason: str | None
    cached: bool
    key: str

    @property
    def truncated(self) -> bool:
        return (self.finish_reason or "").upper() == "MAX_TOKENS"


# (system, user, schema_model) -> RawResponse
Transport = Callable[[str, str, type[BaseModel]], Awaitable[RawResponse]]


class TokenBucket:
    def __init__(self, rpm: int, capacity: int):
        self.rate = max(rpm, 1) / 60.0
        self.capacity = float(max(1, capacity))
        self.tokens = self.capacity
        self.updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                await asyncio.sleep((1 - self.tokens) / self.rate)


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
                 use_db_cache: bool = True, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.s = settings or get_settings()
        self.bucket = TokenBucket(self.s.gemini_rpm, capacity=min(self.s.gemini_concurrency, self.s.gemini_rpm))
        self.sem = asyncio.Semaphore(self.s.gemini_concurrency)
        self.use_db_cache = use_db_cache
        self._sleep = sleep
        self._transport = transport
        self.hits = self.misses = 0

    # ------------------------------------------------------------ public

    async def generate(self, system: str, user: str, schema: type[BaseModel]) -> LLMResult:
        key = cache_key(self.s.gemini_model, self.s.prompt_version, schema, system, user)

        if self.s.llm_mode == "replay":
            raw = self._replay_load(key)
            self.hits += 1
            return LLMResult(_parse(raw.text), raw.text, raw.finish_reason, True, key)

        if self.use_db_cache and (hit := await asyncio.to_thread(self._cache_get, key)):
            self.hits += 1
            return LLMResult(_parse(hit.text), hit.text, hit.finish_reason, True, key)

        self.misses += 1
        raw = await self._call_with_retries(system, user, schema, key)
        if self.use_db_cache:
            await asyncio.to_thread(self._cache_put, key, raw)
        if self.s.llm_record:
            self._replay_save(key, raw)
        return LLMResult(_parse(raw.text), raw.text, raw.finish_reason, False, key)

    # ------------------------------------------------------------ calling

    async def _call_with_retries(self, system: str, user: str, schema: type[BaseModel], key: str) -> RawResponse:
        transport = self._transport or self._genai_transport
        for attempt in range(len(BACKOFF_S) + 1):
            await self.bucket.acquire()
            t0 = time.monotonic()
            try:
                async with self.sem:
                    raw = await asyncio.wait_for(transport(system, user, schema), timeout=self.s.gemini_timeout_s)
                log.info("llm call ok key=%s ms=%d finish=%s", key[:10], (time.monotonic() - t0) * 1000, raw.finish_reason)
                return raw
            except LLMRateLimited as exc:
                if exc.daily:
                    log.warning("llm daily quota exhausted key=%s", key[:10])
                    raise ConanError("LLM_QUOTA") from exc
                if attempt == len(BACKOFF_S):
                    raise ConanError("LLM_QUOTA") from exc
                wait = max(BACKOFF_S[attempt], exc.retry_after or 0)
                log.warning("llm 429 key=%s attempt=%d wait=%.1fs", key[:10], attempt + 1, wait)
                await self._sleep(wait)
            except (LLMUnavailable, asyncio.TimeoutError) as exc:
                if attempt == len(BACKOFF_S):
                    raise ConanError("LLM_UNAVAILABLE") from exc
                log.warning("llm unavailable key=%s attempt=%d err=%s", key[:10], attempt + 1, type(exc).__name__)
                await self._sleep(BACKOFF_S[attempt])
        raise ConanError("LLM_UNAVAILABLE")  # unreachable

    async def _genai_transport(self, system: str, user: str, schema: type[BaseModel]) -> RawResponse:
        from google import genai
        from google.genai import errors, types

        if not self.s.gemini_api_key:
            raise ConanError("LLM_UNAVAILABLE", "GEMINI_API_KEY not set")
        if not hasattr(self, "_genai"):
            self._genai = genai.Client(api_key=self.s.gemini_api_key)
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            response_mime_type="application/json",
            response_schema=schema,
            http_options=types.HttpOptions(timeout=int(self.s.gemini_timeout_s * 1000)),
        )
        try:
            resp = await self._genai.aio.models.generate_content(model=self.s.gemini_model, contents=user, config=config)
        except errors.APIError as exc:
            if exc.code == 429:
                raise _rate_limit_from(exc) from exc
            if exc.code in (500, 502, 503, 504):
                raise LLMUnavailable(str(exc.code)) from exc
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
                s.add(LLMCache(key=key, response={"text": raw.text, "finish_reason": raw.finish_reason}))
                s.commit()

    def _replay_load(self, key: str) -> RawResponse:
        path = REPLAY_DIR / f"{key}.json"
        if not path.exists():
            raise ConanError("LLM_UNAVAILABLE", f"no replay recording for {key[:10]}")
        return RawResponse(**json.loads(path.read_text(encoding="utf-8")))

    def _replay_save(self, key: str, raw: RawResponse) -> None:
        REPLAY_DIR.mkdir(parents=True, exist_ok=True)
        (REPLAY_DIR / f"{key}.json").write_text(
            json.dumps({"text": raw.text, "finish_reason": raw.finish_reason}, ensure_ascii=False), encoding="utf-8")


def _rate_limit_from(exc) -> LLMRateLimited:
    """Read RetryInfo.retryDelay and whether the violated quota is per-day from a 429 body."""
    body = getattr(exc, "details", None) or getattr(exc, "response_json", None) or {}
    blob = json.dumps(body) if not isinstance(body, str) else body
    retry = None
    if m := re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', blob):
        retry = float(m.group(1))
    daily = bool(re.search(r"PerDay", blob))
    return LLMRateLimited(retry_after=retry, daily=daily)
