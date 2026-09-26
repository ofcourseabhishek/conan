"""Regression tests for the post-implementation review fixes."""

import datetime as dt
import uuid
from types import SimpleNamespace as NS

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import get_engine
from app.main import app
from app.models import Contract, Event, Job
from app.pipeline import runner, snapshot
from app.pipeline.conflicts import _NOTICE, _notice_days
from app.pipeline.risk import score_all
from tests.test_review import AS_OF, by_id, seeded  # noqa: F401  (fixture re-use)


# ---- 1. rate limits key on the real client IP behind Render/Cloudflare

def test_client_ip_prefers_cloudflare_then_forwarded_for():
    from app.api.ratelimit import client_ip
    req = lambda h: NS(headers=h, client=NS(host="10.0.0.1"))  # noqa: E731
    assert client_ip(req({"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "9.9.9.9"})) == "1.2.3.4"
    assert client_ip(req({"x-forwarded-for": "5.6.7.8, 10.1.1.1"})) == "5.6.7.8"
    assert client_ip(req({})) == "10.0.0.1"


def test_upload_limit_is_per_visitor_not_global():
    with TestClient(app) as c:
        post = lambda ip: c.post("/api/contracts", headers={"CF-Connecting-IP": ip},  # noqa: E731
                                 files={"file": ("x.pdf", b"not a pdf" * 200, "application/pdf")})
        assert [post("1.1.1.1").status_code for _ in range(11)][-2:] == [415, 429]
        assert post("2.2.2.2").status_code == 415  # a different visitor is unaffected


def test_sample_requests_are_rate_limited(monkeypatch):
    from app.api import contracts
    monkeypatch.setattr(contracts.samples, "limit", 2)
    monkeypatch.setattr(contracts, "SAMPLE_PDF", contracts.SAMPLE_PDF.with_name("missing.pdf"))
    with TestClient(app) as c:
        codes = [c.post("/api/contracts/sample", headers={"CF-Connecting-IP": "3.3.3.3"}).status_code
                 for _ in range(3)]
    assert codes == [404, 404, 429]


# ---- 2. risk never flows through done / waived / rejected obligations

def _o(oid, **kw):
    base = dict(id=oid, status="open", review_state="proposed", modality="must", due_date=None,
                resolution_status="no_deadline", penalty_text=None, amount=None, category="other",
                deadline_rule={}, evidence_status="verified", confidence=0.9)
    return NS(**{**base, **kw})


def _e(a, b):
    return NS(id=uuid.uuid4(), upstream_id=a, downstream_id=b, relation="depends_on", status="confirmed",
              evidence_status="verified", evidence_quote="q", page=1)


def test_inactive_obligation_breaks_the_chain():
    for mid in ({"status": "done"}, {"status": "waived"}, {"review_state": "rejected"}):
        r = score_all([_o("A", status="blocked"), _o("B", **mid), _o("C")], [_e("A", "B"), _e("B", "C")], [],
                      dt.date(2026, 10, 28))
        assert not any(f.factor == "Potential downstream impact" for f in r["C"].factors), mid


# ---- 3. 'other' events list their dependent obligation

def test_other_event_lists_its_dependent(seeded):  # noqa: F811
    client, cid, _ = seeded
    a = client.patch("/api/obligations/O-002", params={"contract_id": cid, **AS_OF},
                     json={"action": "edit", "patch": {"trigger_event": "other"}}).json()
    ev = {e["key"]: e for e in a["events"]}
    assert ev["other:O-002"]["dependent_obligation_ids"] == ["O-002"]


# ---- 4. notice periods written in words

def test_notice_period_word_numbers():
    cases = {"upon sixty days' written notice": 60, "on giving thirty days prior written notice": 30,
             "sixty (60) days' written notice": 60, "on 90 days written notice": 90,
             "one hundred and twenty days notice": 120, "within twenty-one days advance notice": 21}
    for text, days in cases.items():
        assert _notice_days(_NOTICE.search(text)) == days, text


# ---- 5. a live job is never reclaimed; old sample copies are cleaned up

def _job(state="running", minutes_ago=5, **kw):
    with Session(get_engine()) as s:
        c = Contract(name="x", sha256="2" * 64, pipeline_version="v1", **kw)
        s.add(c)
        s.flush()
        j = Job(contract_id=c.id, state=state,
                updated_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago))
        s.add(j)
        s.commit()
        return c.id, j.id


def test_requeue_skips_jobs_this_process_owns():
    _, owned = _job()
    _, orphan = _job()
    runner._owned.add(owned)
    try:
        requeued = runner.requeue_stale_jobs()
    finally:
        runner._owned.discard(owned)
    assert orphan in requeued and owned not in requeued
    with Session(get_engine()) as s:
        assert s.get(Job, owned).attempts == 0


def test_heartbeat_keeps_a_job_fresh():
    _, jid = _job()
    runner._touch(jid)
    assert jid not in runner.requeue_stale_jobs()


def test_old_sample_copies_are_deleted():
    old_cid, _ = _job(state="done", is_sample=True)
    new_cid, _ = _job(state="done", is_sample=True)
    upload_cid, _ = _job(state="done")
    with Session(get_engine()) as s:
        for cid in (old_cid, upload_cid):
            c = s.get(Contract, cid)
            c.created_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
            s.add(c)
        s.commit()
    assert runner.delete_old_samples() >= 1
    with Session(get_engine()) as s:
        assert s.get(Contract, old_cid) is None
        assert s.get(Contract, new_cid) is not None and s.get(Contract, upload_cid) is not None


# ---- 7. a prompt change retires cached analyses

def test_cache_version_tracks_the_prompts(monkeypatch):
    v1 = snapshot.cache_version()
    monkeypatch.setattr(snapshot, "P1_SYSTEM", snapshot.P1_SYSTEM + "\nNew rule.")
    assert snapshot.cache_version() != v1 and snapshot.cache_version().startswith(v1.split("+")[0] + "+")


# ---- 8. completion cascade: rejected duties don't date events; first completion wins

def test_rejected_obligation_does_not_date_its_event(seeded):  # noqa: F811
    client, cid, _ = seeded
    q = {"contract_id": cid, **AS_OF}
    client.patch("/api/obligations/O-001", params=q, json={"action": "reject"})
    a = client.patch("/api/obligations/O-001/status", params=q,
                     json={"status": "done", "occurred_on": "2026-10-01"}).json()
    assert {e["key"]: e for e in a["events"]}["delivery"]["date"] is None
    assert by_id(a)["O-002"]["due_date"] is None


def test_second_producer_does_not_overwrite_first_completion(seeded):  # noqa: F811
    client, cid, _ = seeded
    q = {"contract_id": cid, **AS_OF}
    client.patch("/api/obligations/O-003", params=q,
                 json={"action": "edit", "patch": {"produces_event": "delivery"}})
    client.patch("/api/obligations/O-001/status", params=q, json={"status": "done", "occurred_on": "2026-10-01"})
    a = client.patch("/api/obligations/O-003/status", params=q,
                     json={"status": "done", "occurred_on": "2026-10-09"}).json()
    ev = {e["key"]: e for e in a["events"]}["delivery"]
    assert (ev["date"], ev["source_obligation_id"]) == ("2026-10-01", "O-001")
    with Session(get_engine()) as s:
        assert s.get(Event, (cid, "delivery")).date_source == "completion"
