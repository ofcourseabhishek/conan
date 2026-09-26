"""CP1 path end to end on the in-process app: upload -> job -> clauses in the analysis."""

import datetime as dt
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import get_engine
from app.main import app
from app.models import Contract, Job
from app.pipeline import runner
from tests.pdfgen import build_blank_pdf, build_pdf


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


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
