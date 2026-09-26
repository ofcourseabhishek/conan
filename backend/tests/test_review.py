"""Events API, completion cascade and review mutations on a seeded delivery -> payment chain."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import get_engine
from app.main import app
from app.models import Clause, Contract, Edge, Obligation
from app.pipeline.recompute import recompute

AS_OF = {"as_of": "2026-10-28"}


def rule(value=None, day_type="calendar", anchor=None, kind="relative"):
    r = {"kind": kind, "anchor_event": anchor, "direction": "after", "is_conditional": False}
    if value is not None:
        r["offset"] = {"value": value, "unit": "day", "day_type": day_type}
    return r


def obl(cid, oid, action, trigger, produces, deadline, **kw):
    return Obligation(contract_id=cid, id=oid, clause_id="C01", actor="Velloran Components LLP", action=action,
                      category="delivery", trigger_event=trigger, produces_event=produces, deadline_rule=deadline,
                      evidence_quote=f"quote for {action} with enough characters", evidence_status="verified",
                      page_start=1, page_end=1, confidence=0.9, **kw)


@pytest.fixture()
def seeded():
    with Session(get_engine()) as s:
        c = Contract(name="Chain", sha256="1" * 64, pipeline_version="v1", page_count=1,
                     parties=[{"name": "Velloran Components LLP", "role": "Supplier"}])
        s.add(c)
        s.flush()
        s.add(Clause(contract_id=c.id, id="C01", char_start=0, char_end=10, page_start=1, page_end=1, text="x" * 10))
        s.add_all([
            obl(c.id, "O-001", "deliver", "po_issued", "delivery", rule(10, "business", "po_issued")),
            obl(c.id, "O-002", "inspect", "delivery", "acceptance", rule(5, "business", "delivery")),
            obl(c.id, "O-003", "invoice", "acceptance", "invoice_receipt", rule(kind="none", anchor="acceptance")),
            obl(c.id, "O-004", "pay", "invoice_receipt", "payment", rule(30, "calendar", "invoice_receipt"),
                modality="must"),
        ])
        s.flush()
        edge = Edge(contract_id=c.id, upstream_id="O-001", downstream_id="O-002", relation="must_precede",
                    source="rule", evidence_quote="q", evidence_status="verified", page=1)
        s.add(edge)
        recompute(s, c.id)
        s.commit()
        ids = c.id, edge.id
    with TestClient(app) as client:
        yield client, *ids


def by_id(a):
    return {o["id"]: o for o in a["obligations"]}


def test_events_created_from_triggers_and_products(seeded):
    client, cid, _ = seeded
    a = client.get(f"/api/contracts/{cid}/analysis", params=AS_OF).json()
    ev = {e["key"]: e for e in a["events"]}
    assert set(ev) == {"po_issued", "delivery", "acceptance", "invoice_receipt", "payment"}
    assert ev["delivery"]["source_obligation_id"] == "O-001" and ev["delivery"]["dependent_obligation_ids"] == ["O-002"]
    assert ev["invoice_receipt"]["label"] == "Invoice received"
    assert a["stats"]["unresolved_dates"] == 3


def test_setting_an_event_resolves_dependents(seeded):
    client, cid, _ = seeded
    a = client.put(f"/api/contracts/{cid}/events/invoice_receipt", params=AS_OF, json={"date": "2026-10-03"}).json()
    pay = by_id(a)["O-004"]
    assert (pay["due_date"], pay["date_provenance"], pay["resolution_status"]) == ("2026-11-02", "user_event", "resolved")
    assert pay["resolution_trace"] == "invoice_receipt (2026-10-03, user-set) + 30 calendar days → 2026-11-02"
    assert any(f["factor"] == "Due within 7 days" for f in pay["risk"]["factors"])
    assert a["review_actions"][-1]["action"] == "set_date"
    cleared = client.put(f"/api/contracts/{cid}/events/invoice_receipt", params=AS_OF, json={"date": None}).json()
    assert by_id(cleared)["O-004"]["due_date"] is None
    assert client.put(f"/api/contracts/{cid}/events/nope", json={"date": None}).status_code == 404


def test_completion_cascade_and_undo(seeded):
    client, cid, _ = seeded
    client.put(f"/api/contracts/{cid}/events/po_issued", json={"date": "2026-09-21"})
    a = client.patch("/api/obligations/O-001/status", params={"contract_id": cid, **AS_OF},
                     json={"status": "done", "occurred_on": "2026-10-01"}).json()
    o = by_id(a)
    assert o["O-001"]["status"] == "done" and o["O-001"]["risk"]["score"] == 0
    assert (o["O-002"]["due_date"], o["O-002"]["date_provenance"]) == ("2026-10-08", "completion")
    ev = {e["key"]: e for e in a["events"]}["delivery"]
    assert (ev["date"], ev["date_source"]) == ("2026-10-01", "completion")

    undo = client.patch("/api/obligations/O-001/status", params={"contract_id": cid}, json={"status": "open"}).json()
    assert by_id(undo)["O-002"]["due_date"] is None
    assert {e["key"]: e for e in undo["events"]}["delivery"]["date"] is None


def test_blocked_propagates_downstream(seeded):
    client, cid, _ = seeded
    a = client.patch("/api/obligations/O-001/status", params={"contract_id": cid, **AS_OF},
                     json={"status": "blocked"}).json()
    impact = [f for f in by_id(a)["O-002"]["risk"]["factors"] if f["factor"] == "Potential downstream impact"]
    assert impact[0]["points"] == 24 and impact[0]["path"][0]["upstream_id"] == "O-001"


def test_confirm_edit_reject_with_audit(seeded):
    client, cid, _ = seeded
    q = {"contract_id": cid, **AS_OF}
    a = client.patch("/api/obligations/O-004", params=q, json={"action": "confirm", "note": "checked"}).json()
    assert by_id(a)["O-004"]["review_state"] == "confirmed"

    patch = {"action": "edit", "patch": {"penalty_text": "interest at 1.5% per month", "trigger_event": "delivery"}}
    a = client.patch("/api/obligations/O-004", params=q, json=patch).json()
    o = by_id(a)["O-004"]
    assert o["review_state"] == "edited" and o["field_provenance"]["penalty_text"] == "user"
    assert o["deadline_rule"]["anchor_event"] == "delivery"
    last = a["review_actions"][-1]
    assert last["action"] == "edit" and last["before"] == {"penalty_text": None, "trigger_event": "invoice_receipt"}

    a = client.patch("/api/obligations/O-004", params=q, json={"action": "reject"}).json()
    assert by_id(a)["O-004"]["risk"]["score"] == 0
    assert client.patch("/api/obligations/O-999", params=q, json={"action": "confirm"}).status_code == 404
    assert client.patch("/api/obligations/O-004", params=q, json={"action": "edit"}).status_code == 422


def test_reviewer_entered_date(seeded):
    client, cid, _ = seeded
    patch = {"action": "edit", "patch": {"deadline_rule": {"kind": "absolute", "absolute_date": "2027-01-15"}}}
    a = client.patch("/api/obligations/O-003", params={"contract_id": cid}, json=patch).json()
    o = by_id(a)["O-003"]
    assert (o["due_date"], o["date_provenance"]) == ("2027-01-15", "user_event")


def test_edge_confirm_reject_and_reviewed_only(seeded):
    client, cid, eid = seeded
    a = client.get(f"/api/contracts/{cid}/analysis", params={"reviewed_only": True}).json()
    assert a["edges"][0]["propagates"] is False
    a = client.patch(f"/api/edges/{eid}", params={"reviewed_only": True}, json={"action": "confirm"}).json()
    assert a["edges"][0]["status"] == "confirmed" and a["edges"][0]["propagates"] is True
    a = client.patch(f"/api/edges/{eid}", json={"action": "reject"}).json()
    assert a["edges"][0]["propagates"] is False and a["edges"][0]["reject_reason"] == "reviewer"
    assert client.patch(f"/api/edges/{uuid.uuid4()}", json={"action": "confirm"}).status_code == 404
