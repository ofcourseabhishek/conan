"""CP1 path end to end on the in-process app: upload -> job -> clauses in the analysis."""

import datetime as dt
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import get_engine
from app.config import Settings
from app.main import app
from app.models import Contract, Job
from app.pipeline import runner
from app.pipeline.gemini import GeminiClient
from tests.fakes import demo_llm, fake_p1
from tests.pdfgen import build_blank_pdf, build_pdf


@pytest.fixture()
def client():
    runner.set_llm_client(GeminiClient(Settings(gemini_rpm=6000, prompt_version=f"api-{uuid.uuid4()}"),
                                       transport=fake_p1))
    with TestClient(app) as c:
        yield c
    runner.set_llm_client(None)


def wait_job(client, job_id, timeout=10):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("done", "done_with_warnings", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def upload(client, data: bytes, name="MSA.pdf"):
    return client.post("/api/contracts", files={"file": (name, data, "application/pdf")})


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] and body["db"]


def test_upload_to_clauses(client):
    r = upload(client, build_pdf(), name="../../etc/Velloran MSA<script>.pdf")
    assert r.status_code == 202
    body = r.json()
    job = wait_job(client, body["job_id"])
    assert job["state"] == "done", job
    assert job["progress_pct"] == 100 and job["stage"] == "done"

    a = client.get(f"/api/contracts/{body['contract_id']}/analysis", params={"as_of": "2026-10-28"}).json()
    assert a["as_of"] == "2026-10-28"
    assert a["contract"]["name"] == "Velloran MSA script"  # sanitized, never a path
    assert a["contract"]["page_count"] == 3
    assert [p["role"] for p in a["contract"]["parties"]] == ["Customer", "Supplier"]
    refs = [c["section_ref"] for c in a["clauses"]]
    assert "6.3" in refs and "Sch. B" in refs
    assert a["stats"]["clauses"] == len(refs) and a["disclaimer"]

    obls = a["obligations"]
    assert [o["id"] for o in obls] == [f"O-{i:03d}" for i in range(1, len(obls) + 1)]
    pay = next(o for o in obls if o["evidence_quote"].startswith("Customer shall pay all undisputed"))
    assert pay["actor"] == "Tarnwick Robotics Pvt. Ltd." and pay["evidence_status"] == "verified"
    assert pay["page_start"] == 2 and not pay["page_approx"]
    doc_clause = next(c for c in a["clauses"] if c["id"] == pay["clause_id"])
    rel = pay["evidence_start"] - doc_clause["char_start"], pay["evidence_end"] - doc_clause["char_start"]
    assert " ".join(doc_clause["text"][rel[0]:rel[1]].split()) == pay["evidence_quote"]
    assert pay["risk"]["factors"] == [] and pay["risk"]["band"] == "low"
    assert a["stats"]["obligations"] == len(obls) and a["stats"]["clauses_without_obligations"] >= 1
    states = {c["section_ref"]: c["extraction_state"] for c in a["clauses"]}
    assert states["6.3"] == "ok" and states["1.1"] == "no_obligations"


def test_not_pdf_rejected_before_any_work(client):
    r = upload(client, b"MZ" + b"\0" * 5000, name="evil.exe")
    assert r.status_code == 415 and r.json()["error_code"] == "NOT_PDF"


def test_scanned_pdf_fails_job_with_code(client):
    body = upload(client, build_blank_pdf(2)).json()
    job = wait_job(client, body["job_id"])
    assert job["state"] == "failed" and job["error_code"] == "NO_TEXT_LAYER"
    assert "scanned" in job["error_message"]


def test_delete_cascades(client):
    body = upload(client, build_pdf()).json()
    wait_job(client, body["job_id"])
    assert client.delete(f"/api/contracts/{body['contract_id']}").status_code == 204
    assert client.get(f"/api/contracts/{body['contract_id']}/analysis").status_code == 404
    assert client.get(f"/api/jobs/{body['job_id']}").status_code == 404


def test_stale_running_job_is_requeued_and_gives_up_after_three_attempts():
    with Session(get_engine()) as s:
        c = Contract(name="x", sha256="0" * 64, pipeline_version="v1")
        s.add(c)
        s.flush()
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)
        fresh = Job(contract_id=c.id, state="running", updated_at=dt.datetime.now(dt.timezone.utc))
        stale = Job(contract_id=c.id, state="running", updated_at=old)
        dead = Job(contract_id=c.id, state="running", updated_at=old, attempts=3)
        s.add_all([fresh, stale, dead])
        s.commit()
        ids = fresh.id, stale.id, dead.id
    requeued = runner.requeue_stale_jobs()
    assert ids[1] in requeued and ids[0] not in requeued and ids[2] not in requeued
    with Session(get_engine()) as s:
        assert s.get(Job, ids[2]).state == "failed"
        assert s.get(Job, ids[1]).attempts == 1


def test_demo_story_end_to_end():
    """CP3 rehearsal: upload -> obligations -> links -> set PO date -> block delivery -> downstream impact."""
    runner.set_llm_client(GeminiClient(Settings(gemini_rpm=6000, prompt_version=f"demo-{uuid.uuid4()}"),
                                       transport=demo_llm))
    try:
        with TestClient(app) as client:
            body = upload(client, build_pdf()).json()
            job = wait_job(client, body["job_id"])
            assert job["state"] == "done", job
            cid = body["contract_id"]
            a = client.get(f"/api/contracts/{cid}/analysis", params={"as_of": "2026-10-28"}).json()
            obls = {o["action"]: o for o in a["obligations"]}
            assert list(obls) == ["deliver", "inspect", "invoice", "pay"]
            assert all(o["evidence_status"] == "verified" for o in obls.values())
            links = {(e["upstream_id"], e["downstream_id"], e["relation"], e["source"]) for e in a["edges"]}
            d, i, v, p = (obls[k]["id"] for k in ("deliver", "inspect", "invoice", "pay"))
            assert {(d, i, "must_precede", "rule"), (i, v, "must_precede", "rule"), (v, p, "must_precede", "rule"),
                    (i, v, "condition_for", "llm")} <= links
            assert a["stats"]["unresolved_dates"] == 3

            a = client.put(f"/api/contracts/{cid}/events/po_issued", params={"as_of": "2026-10-28"},
                           json={"date": "2026-10-20"}).json()
            assert next(o for o in a["obligations"] if o["id"] == d)["due_date"] == "2026-11-03"

            a = client.patch(f"/api/obligations/{d}/status", params={"contract_id": cid, "as_of": "2026-10-28"},
                             json={"status": "blocked"}).json()
            risk = {o["id"]: o["risk"] for o in a["obligations"]}
            impact = lambda oid: next((f for f in risk[oid]["factors"] if f["factor"] == "Potential downstream impact"), None)  # noqa: E731
            assert impact(i)["points"] == 24 and impact(i)["path"][0]["upstream_id"] == d
            assert impact(v)["points"] == 15 and impact(p)["points"] > 0
            assert risk[d]["score"] == 57 and risk[d]["band"] == "high"  # 20 due soon + 30 blocked + 7 delivery
    finally:
        runner.set_llm_client(None)


def test_cors_origin_regex_allows_deployment_urls():
    """Vercel gives every deploy its own URL; ALLOWED_ORIGIN_REGEX lets those through without listing each."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    probe = FastAPI()
    probe.add_middleware(CORSMiddleware, allow_origins=["https://app-conan.vercel.app"],
                         allow_origin_regex=r"https://conan-[a-z0-9]+-codedsuperhero\.vercel\.app",
                         allow_methods=["POST"], allow_headers=["*"])

    @probe.post("/x")
    def x():
        return {}

    with TestClient(probe) as c:
        pre = lambda o: c.options("/x", headers={"Origin": o, "Access-Control-Request-Method": "POST"}).status_code  # noqa: E731
        assert pre("https://app-conan.vercel.app") == 200
        assert pre("https://conan-pcc598ne1-codedsuperhero.vercel.app") == 200
        assert pre("https://conan-pcc598ne1-codedsuperhero.vercel.app.evil.example") == 400  # full match only
        assert pre("https://evil.example") == 400
