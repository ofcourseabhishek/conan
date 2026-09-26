"""Gemini client behaviour with a fake transport: no network (TRD §13 'forced-429 test')."""

import asyncio
import itertools

import pytest

from app.config import Settings
from app.errors import ConanError
from app.pipeline.gemini import GeminiClient, LLMRateLimited, LLMUnavailable, RawResponse, TokenBucket, cache_key
from app.pipeline.llm_schemas import P1Response

OK = RawResponse('{"clauses": [], "obligations": []}', "STOP")
_n = itertools.count()


def settings(**kw) -> Settings:
    base = dict(gemini_rpm=6000, gemini_concurrency=2, prompt_version=f"test-{next(_n)}")
    return Settings(**{**base, **kw})


class Fake:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def __call__(self, system, user, schema, api_key=""):
        self.calls += 1
        out = self.outcomes.pop(0) if self.outcomes else OK
        if isinstance(out, Exception):
            raise out
        return out


class Sleeps:
    """Virtual time: sleeping records the wait and advances the clock instantly."""
    def __init__(self):
        self.waits = []
        self.t = 1000.0

    def now(self) -> float:
        return self.t

    async def __call__(self, s):
        self.waits.append(round(s, 6))
        self.t += s


def vclient(fake, sleeps=None, **kw) -> GeminiClient:
    sleeps = sleeps or Sleeps()
    return GeminiClient(settings(**kw), transport=fake, use_db_cache=False, sleep=sleeps, clock=sleeps.now)


async def test_success_parses_json():
    c = GeminiClient(settings(), transport=Fake(), use_db_cache=False)
    r = await c.generate("sys", "user", P1Response)
    assert r.data == {"clauses": [], "obligations": []} and not r.cached and not r.truncated


async def test_429_backs_off_honouring_retry_after_then_succeeds():
    fake, sleeps = Fake(LLMRateLimited(retry_after=13), LLMRateLimited(), OK), Sleeps()
    c = vclient(fake, sleeps)
    r = await c.generate("sys", "user", P1Response)
    assert r.data is not None and fake.calls == 3
    assert sleeps.waits == [13, 4.0]  # max(backoff, Retry-After), then plain backoff


async def test_persistent_429_raises_llm_quota_after_three_retries():
    fake = Fake(*[LLMRateLimited()] * 4)
    c = vclient(fake)
    with pytest.raises(ConanError) as ei:
        await c.generate("sys", "user", P1Response)
    assert ei.value.code == "LLM_QUOTA" and fake.calls == 4


async def test_daily_quota_fails_fast():
    fake = Fake(LLMRateLimited(daily=True))
    c = vclient(fake)
    with pytest.raises(ConanError) as ei:
        await c.generate("sys", "user", P1Response)
    assert ei.value.code == "LLM_QUOTA" and fake.calls == 1


async def test_server_errors_become_llm_unavailable():
    fake = Fake(*[LLMUnavailable("503")] * 4)
    c = vclient(fake)
    with pytest.raises(ConanError) as ei:
        await c.generate("sys", "user", P1Response)
    assert ei.value.code == "LLM_UNAVAILABLE"


async def test_memoized_in_db_so_restart_replays_for_free():
    s = settings()
    fake = Fake()
    first = await GeminiClient(s, transport=fake).generate("sys", "same input", P1Response)
    again = GeminiClient(s, transport=fake)  # a fresh client, as after a Render restart
    second = await again.generate("sys", "same input", P1Response)
    assert fake.calls == 1 and not first.cached and second.cached and second.data == first.data
    assert again.hits == 1 and again.misses == 0


def test_cache_key_changes_with_every_component():
    base = ("m", "p1", P1Response, "sys", "in")
    keys = {cache_key(*base), cache_key("m2", *base[1:]), cache_key("m", "p2", *base[2:]),
            cache_key(*base[:3], "sys2", "in"), cache_key(*base[:4], "in2")}
    assert len(keys) == 5


async def test_truncated_and_non_json_responses_are_reported_not_raised():
    fake = Fake(RawResponse('{"clauses": [', "MAX_TOKENS"))
    r = await GeminiClient(settings(), transport=fake, use_db_cache=False).generate("s", "u", P1Response)
    assert r.data is None and r.truncated


async def test_replay_mode_without_recording_is_unavailable():
    c = GeminiClient(settings(llm_mode="replay"), transport=Fake(), use_db_cache=False)
    with pytest.raises(ConanError) as ei:
        await c.generate("s", "never recorded", P1Response)
    assert ei.value.code == "LLM_UNAVAILABLE"


async def test_token_bucket_spaces_calls():
    bucket = TokenBucket(rpm=600, capacity=1)  # one call per 0.1 s
    t0 = asyncio.get_running_loop().time()
    for _ in range(4):
        await bucket.acquire()
    assert asyncio.get_running_loop().time() - t0 >= 0.28



# ---------------------------------------------------------------- multiple API keys


class ByKey:
    """Fake transport whose behaviour depends on which key is used; records the key per call."""
    def __init__(self, per_key=None):
        self.per_key = {k: list(v) for k, v in (per_key or {}).items()}
        self.used = []

    async def __call__(self, system, user, schema, api_key=""):
        self.used.append(api_key)
        queue = self.per_key.get(api_key)
        out = queue.pop(0) if queue else OK
        if isinstance(out, Exception):
            raise out
        return out


def test_api_keys_merge_and_dedupe():
    s = Settings(gemini_api_key="k1", gemini_api_keys=" k2, k1 ,,k3 ")
    assert s.api_keys == ["k1", "k2", "k3"]
    assert Settings(gemini_api_key=None, gemini_api_keys=None).api_keys == []


async def test_calls_spread_across_keys():
    fake = ByKey()
    c = vclient(fake, gemini_api_key="k1", gemini_api_keys="k2")
    for i in range(4):
        await c.generate("s", f"u{i}", P1Response)
    assert sorted(fake.used) == ["k1", "k1", "k2", "k2"]


async def test_each_key_has_its_own_rate_limit():
    sleeps = Sleeps()
    fake = ByKey()
    c = vclient(fake, sleeps, gemini_api_key="k1", gemini_api_keys="k2,k3", gemini_rpm=1, gemini_concurrency=1)
    for i in range(3):
        await c.generate("s", f"u{i}", P1Response)
    assert sorted(fake.used) == ["k1", "k2", "k3"] and sleeps.waits == []  # 3 keys x 1 RPM: no waiting
    await c.generate("s", "u4", P1Response)
    assert sleeps.waits == [60.0]  # the 4th call waits for a refill


async def test_per_minute_429_fails_over_to_next_key_without_waiting():
    sleeps = Sleeps()
    fake = ByKey({"k1": [LLMRateLimited(retry_after=30)]})
    c = vclient(fake, sleeps, gemini_api_key="k1", gemini_api_keys="k2")
    r = await c.generate("s", "u", P1Response)
    assert r.data is not None and fake.used == ["k1", "k2"] and sleeps.waits == []


async def test_daily_quota_parks_key_and_uses_the_rest():
    fake = ByKey({"k1": [LLMRateLimited(daily=True)]})
    c = vclient(fake, gemini_api_key="k1", gemini_api_keys="k2")
    for i in range(3):
        await c.generate("s", f"u{i}", P1Response)
    assert fake.used == ["k1", "k2", "k2", "k2"] and c.pool.available() == 1


async def test_all_keys_out_for_the_day_raises_llm_quota():
    fake = ByKey({"k1": [LLMRateLimited(daily=True)], "k2": [LLMRateLimited(daily=True)]})
    c = vclient(fake, gemini_api_key="k1", gemini_api_keys="k2")
    with pytest.raises(ConanError) as ei:
        await c.generate("s", "u", P1Response)
    assert ei.value.code == "LLM_QUOTA" and sorted(fake.used) == ["k1", "k2"] and c.pool.available() == 0


def test_quota_reset_is_next_midnight_pacific():
    import datetime as dt

    from app.pipeline.gemini import seconds_until_quota_reset
    at = dt.datetime(2026, 9, 26, 6, 0, tzinfo=dt.timezone.utc)  # 23:00 PDT on the 25th
    assert seconds_until_quota_reset(at) == 3600 + 60


async def test_empty_key_is_refused_by_real_transport():
    c = GeminiClient(settings(), use_db_cache=False)
    with pytest.raises(ConanError) as ei:
        await c.generate("s", "u", P1Response)
    assert ei.value.code == "LLM_UNAVAILABLE"
