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

    async def __call__(self, system, user, schema):
        self.calls += 1
        out = self.outcomes.pop(0) if self.outcomes else OK
        if isinstance(out, Exception):
            raise out
        return out


class Sleeps:
    def __init__(self):
        self.waits = []

    async def __call__(self, s):
        self.waits.append(s)


async def test_success_parses_json():
    c = GeminiClient(settings(), transport=Fake(), use_db_cache=False)
    r = await c.generate("sys", "user", P1Response)
    assert r.data == {"clauses": [], "obligations": []} and not r.cached and not r.truncated


async def test_429_backs_off_honouring_retry_after_then_succeeds():
    fake, sleeps = Fake(LLMRateLimited(retry_after=13), LLMRateLimited(), OK), Sleeps()
    c = GeminiClient(settings(), transport=fake, use_db_cache=False, sleep=sleeps)
    r = await c.generate("sys", "user", P1Response)
    assert r.data is not None and fake.calls == 3
    assert sleeps.waits == [13, 4.0]  # max(backoff, Retry-After), then plain backoff


async def test_persistent_429_raises_llm_quota_after_three_retries():
    fake = Fake(*[LLMRateLimited()] * 4)
    c = GeminiClient(settings(), transport=fake, use_db_cache=False, sleep=Sleeps())
    with pytest.raises(ConanError) as ei:
        await c.generate("sys", "user", P1Response)
    assert ei.value.code == "LLM_QUOTA" and fake.calls == 4


async def test_daily_quota_fails_fast():
    fake = Fake(LLMRateLimited(daily=True))
    c = GeminiClient(settings(), transport=fake, use_db_cache=False, sleep=Sleeps())
    with pytest.raises(ConanError) as ei:
        await c.generate("sys", "user", P1Response)
    assert ei.value.code == "LLM_QUOTA" and fake.calls == 1


async def test_server_errors_become_llm_unavailable():
    fake = Fake(*[LLMUnavailable("503")] * 4)
    c = GeminiClient(settings(), transport=fake, use_db_cache=False, sleep=Sleeps())
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
