"""D2 conflicts (TRD §9.4): the planted §6.3 vs Schedule B case, other mismatch kinds, notice periods,
no false flags within a clause, LLM conflicts need verified quotes, dismiss survives recompute."""

import uuid
from types import SimpleNamespace as NS

from app.pipeline.conflicts import action_stem, llm_conflicts, merge_rule_conflicts, rule_conflicts
from app.pipeline.llm_schemas import P2Conflict
from tests.test_review import AS_OF, seeded  # noqa: F401  (fixture re-use)

CID = uuid.uuid4()
CLAUSES = [NS(id="C08", section_ref="6.3", page_start=2, text="6.3 Payment. Customer shall pay ..."),
           NS(id="C10", section_ref="Sch. B", page_start=3, text="Payment terms: Net 45 from the date of invoice."),
           NS(id="C11", section_ref="11.1", page_start=5,
              text="11.1 Renewal. Either party may terminate by giving sixty (60) days' prior written notice."),
           NS(id="C12", section_ref="12.1", page_start=6,
              text="12.1 Termination. Either party may terminate for convenience on 90 days written notice.")]


def o(oid, clause, days=30, day_type="calendar", unit="day", action="pay", actor="Tarnwick Robotics Pvt. Ltd.",
      category="payment", trigger="invoice_receipt", amount=None, **kw):
    base = dict(id=oid, clause_id=clause, actor=actor, action=action, object="undisputed amounts", category=category,
                trigger_event=trigger, review_state="proposed", status="open", amount=amount, page_start=2,
                evidence_quote=f"quote {oid}",
                deadline_rule={"kind": "relative", "anchor_event": trigger,
                               "offset": {"value": days, "unit": unit, "day_type": day_type}})
    return NS(**{**base, **kw})


def test_planted_payment_terms_conflict():
    obls = [o("O-005", "C08", 30, "unspecified"), o("O-006", "C10", 45, "unspecified", page_start=3)]
    [c] = rule_conflicts(CID, obls, CLAUSES)
    assert c.kind == "offset_mismatch" and c.obligation_ids == ["O-005", "O-006"]
    assert c.description.startswith("§6.3 (p. 2) sets: pay undisputed amounts within 30 days of invoice receipt; "
                                    "Sch. B (p. 3) sets: pay undisputed amounts within 45 days of invoice receipt.")
    assert c.description.endswith("does not determine which prevails; check the order-of-precedence clause "
                                  "or ask counsel.")


def test_other_kinds_and_non_conflicts():
    assert rule_conflicts(CID, [o("A", "C08", 4, unit="week"), o("B", "C10", 28)], CLAUSES) == []  # 4 weeks = 28 days
    [c] = rule_conflicts(CID, [o("A", "C08", 10, "business"), o("B", "C10", 10, "calendar")], CLAUSES)
    assert c.kind == "day_type_mismatch"
    assert rule_conflicts(CID, [o("A", "C08", 10, "business"), o("B", "C10", 10, "unspecified")], CLAUSES) == []
    [c] = rule_conflicts(CID, [o("A", "C08", amount={"value": 1840000, "currency": "INR"}),
                               o("B", "C10", amount={"value": 1900000, "currency": "INR"})], CLAUSES)
    assert c.kind == "amount_mismatch" and "INR 1,840,000" in c.description
    assert rule_conflicts(CID, [o("A", "C08"), o("B", "C08", 45)], CLAUSES) == []  # same clause: not a conflict
    assert rule_conflicts(CID, [o("A", "C08"), o("B", "C10", 45, actor="Velloran Components LLP")], CLAUSES) == []
    assert rule_conflicts(CID, [o("A", "C08"), o("B", "C10", 45, review_state="rejected")], CLAUSES) == []
    assert action_stem("make payment of") == "pay" and action_stem("remit") == "pay"


def test_notice_periods_compared_within_category():
    obls = [o("O-010", "C11", category="termination", action="terminate", trigger=None),
            o("O-011", "C12", category="termination", action="give notice", trigger="notice_given")]
    [c] = [x for x in rule_conflicts(CID, obls, CLAUSES) if x.kind == "notice_period"]
    assert "60 days' notice for termination" in c.description and "90 days' notice" in c.description
    assert c.quote_a.endswith("sixty (60) days' prior written notice")


def test_llm_conflicts_need_both_quotes_verified():
    doc = CLAUSES[0].text + "\n" + CLAUSES[1].text + "\n"
    obls = [o("O-005", "C08"), o("O-006", "C10")]
    good = P2Conflict(obligation_a="O-005", obligation_b="O-006", quote_a="6.3 Payment. Customer shall pay",
                      quote_b="Payment terms: Net 45 from the date of invoice", description="30 vs 45 days")
    bad = P2Conflict(obligation_a="O-005", obligation_b="O-006", quote_a="6.3 Payment. Customer shall pay",
                     quote_b="Payment terms: Net 60 from receipt of goods", description="made up")
    out = llm_conflicts(CID, [good, bad], obls, doc, [(0, len(doc))])
    assert len(out) == 1 and out[0].source == "llm" and out[0].description.startswith("AI flag (p. 1 vs p. 1)")


def test_merge_keeps_dismissed():
    a = rule_conflicts(CID, [o("A", "C08"), o("B", "C10", 45)], CLAUSES)[0]
    a.status = "dismissed"
    fresh = rule_conflicts(CID, [o("A", "C08"), o("B", "C10", 45)], CLAUSES)
    to_add, to_delete = merge_rule_conflicts([a], fresh)
    assert to_add == [] and to_delete == [] and a.status == "dismissed"
    to_add, to_delete = merge_rule_conflicts([a], [])
    assert to_delete == [a]


def test_conflict_dismiss_survives_recompute_and_reopens(seeded):  # noqa: F811
    from sqlmodel import Session

    from app.db import get_engine
    from app.models import Clause, Obligation
    from tests.test_review import obl, rule

    client, cid, _ = seeded
    with Session(get_engine()) as s:  # a Schedule-style clause that restates O-004's payment with 45 days
        s.add(Clause(contract_id=cid, id="C02", section_ref="Sch. B", char_start=20, char_end=40,
                     page_start=3, page_end=3, text="Payment terms: Net 45"))
        s.add(obl(cid, "O-005", "pay", "invoice_receipt", "payment", rule(45, "calendar", "invoice_receipt"),
                  modality="must"))
        s.commit()
        o5 = s.get(Obligation, (cid, "O-005"))
        o5.clause_id, o5.page_start = "C02", 3
        s.add(o5)
        s.commit()
    a = client.put(f"/api/contracts/{cid}/events/po_issued", params=AS_OF, json={"date": "2026-10-01"}).json()
    [c] = a["conflicts"]
    assert c["kind"] == "offset_mismatch" and c["obligation_ids"] == ["O-004", "O-005"] and c["status"] == "open"
    assert any(f["factor"] == "Part of a flagged conflict" for o in a["obligations"] if o["id"] == "O-004"
               for f in o["risk"]["factors"])

    a = client.patch(f"/api/conflicts/{c['id']}", params=AS_OF, json={"action": "dismiss"}).json()
    assert a["conflicts"][0]["status"] == "dismissed" and a["review_actions"][-1]["target_type"] == "conflict"
    assert not any(f["factor"] == "Part of a flagged conflict" for o in a["obligations"] for f in o["risk"]["factors"])
    a = client.put(f"/api/contracts/{cid}/events/po_issued", params=AS_OF, json={"date": "2026-10-02"}).json()
    assert a["conflicts"][0]["status"] == "dismissed"  # survives recompute
    a = client.patch(f"/api/conflicts/{c['id']}", json={"action": "reopen"}).json()
    assert a["conflicts"][0]["status"] == "open"
