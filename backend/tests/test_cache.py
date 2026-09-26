"""Analysis cache + sample (TRD §10, plan §13): same PDF -> cloned in one request and labelled;
clones are independent; partial results are never cached; /sample works cold and warm."""

import hashlib
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import Settings
from app.db import get_engine
from app.main import app
from app.models import AnalysisCache
from app.pipeline import runner
from app.pipeline.gemini import GeminiClient, RawResponse
from tests.fakes import demo_llm
from tests.pdfgen import build_pdf
from tests.test_api import upload, wait_job


def _client(transport):
    runner.set_llm_client(GeminiClient(Settings(gemini_rpm=6000, prompt_version=f"c-{uuid.uuid4()}"),
                                       transport=transport))
    return TestClient(app)


def _analysis(client, cid):
    return client.get(f"/api/contracts/{cid}/analysis", params={"as_of": "2026-10-28"}).json()


def test_second_upload_is_served_from_cache_and_is_independent():
    calls = []

    async def counting(system, user, schema, api_key="", model=""):
        calls.append(1)
        return await demo_llm(system, user, schema)

    try:
        with _client(counting) as client:
            pdf = build_pdf()  # built once: PyMuPDF stamps a new ID per build, so bytes differ per call
            first = upload(client, pdf).json()
            assert first["cached"] is False
            wait_job(client, first["job_id"])
            n_calls = len(calls)

            r = upload(client, pdf, name="copy.pdf")
            assert r.status_code == 200 and r.json()["cached"] is True
            second = r.json()
            assert client.get(f"/api/jobs/{second['job_id']}").json()["state"] == "done"
            assert len(calls) == n_calls  # no LLM call for the cached copy

            a1, a2 = _analysis(client, first["contract_id"]), _analysis(client, second["contract_id"])
            assert a1["contract"]["cached_at"] is None and a2["contract"]["cached_at"] is not None
            assert a2["contract"]["name"] == "copy"
            strip = lambda a: [(o["id"], o["action"], o["evidence_start"], o["page_start"]) for o in a["obligations"]]  # noqa: E731
            assert strip(a1) == strip(a2) and len(a2["edges"]) == len(a1["edges"])
            assert {e["id"] for e in a1["edges"]}.isdisjoint({e["id"] for e in a2["edges"]})

            # independent copies: blocking delivery in the clone leaves the original alone
            d = a2["obligations"][0]["id"]
            client.patch(f"/api/obligations/{d}/status", params={"contract_id": second["contract_id"]},
                         json={"status": "blocked"})
            assert _analysis(client, first["contract_id"])["obligations"][0]["status"] == "open"
    finally:
        runner.set_llm_client(None)


def test_partial_extraction_is_not_cached():
    async def flaky(system, user, schema, api_key="", model=""):
        if user.startswith("OBLIGATIONS"):
            return await demo_llm(system, user, schema)
        if "6.3 Payment" in user:
            return RawResponse("not json", "STOP")
        return await demo_llm(system, user, schema)

    from app.config import get_settings
    get_settings().batch_chars = 300  # several batches, so one can fail alone
    try:
        with _client(flaky) as client:
            pdf = build_pdf()
            body = upload(client, pdf).json()
            job = wait_job(client, body["job_id"])
            assert job["state"] == "done_with_warnings" and job["error_code"] == "PARTIAL_EXTRACTION"
            with Session(get_engine()) as s:
                assert s.get(AnalysisCache, (hashlib.sha256(pdf).hexdigest(), get_settings().pipeline_version)) is None
    finally:
        get_settings().batch_chars = 8000
        runner.set_llm_client(None)


def test_sample_cold_then_warm():
    try:
        with _client(demo_llm) as client:
            cold = client.post("/api/contracts/sample")
            assert cold.status_code == 202 and cold.json()["cached"] is False
            wait_job(client, cold.json()["job_id"])
            warm = client.post("/api/contracts/sample")
            assert warm.status_code == 200 and warm.json()["cached"] is True
            a = _analysis(client, warm.json()["contract_id"])
            assert a["contract"]["is_sample"] and a["contract"]["name"].startswith("Sample:")
            assert len(a["obligations"]) == 4
    finally:
        runner.set_llm_client(None)
