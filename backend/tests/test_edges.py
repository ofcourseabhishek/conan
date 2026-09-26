"""Edges (TRD §9.3, §13): rule edges, P2 validation (bad IDs, self-loops, unverified quotes),
rule-wins dedupe, cycle breaking, P2 failure fallback, rule refresh after review."""

import json
import uuid
from types import SimpleNamespace as NS

from app.config import Settings
from app.models import Edge
from app.pipeline.edges import (
    break_cycles, build_edges, refresh_rule_edges, render_p2, rule_edges, validate_llm_edges,
)
from app.pipeline.gemini import GeminiClient, LLMUnavailable, RawResponse
from app.pipeline.llm_schemas import P2Edge
from tests.test_review import AS_OF, by_id, seeded  # noqa: F401  (fixture re-use)

CID = uuid.uuid4()

TEXTS = {
    "C03": "3.1 Delivery. Supplier shall deliver the Goods within ten (10) Business Days of the Purchase Order.",
    "C05": "5.1 Inspection. Subject to Section 3.1, Customer shall inspect the Goods within five (5) Business "
           "Days of delivery.",
    "C09": "6.3 Payment. Customer shall pay within thirty (30) days of receipt of a valid invoice.",
    "C12": "8.2 Liquidated Damages. If Supplier fails to deliver under Section 3.1, Supplier shall pay "
           "liquidated damages of 0.5% per week.",
}
REFS = {"C03": "3.1", "C05": "5.1", "C09": "6.3", "C12": "8.2"}


def _doc():
    doc, clauses = "", []
    for cid, text in TEXTS.items():
        clauses.append(NS(id=cid, section_ref=REFS[cid], char_start=len(doc), char_end=len(doc) + len(text), text=text))
        doc += text + "\n"
    return doc, clauses, [(0, len(doc))]


def o(oid, clause, trig=None, prod=None, **kw):
    base = dict(id=oid, clause_id=clause, trigger_event=trig, produces_event=prod, review_state="proposed",
                deadline_rule={"anchor_event": trig, "raw_text": f"raw {oid}"}, evidence_quote=f"quote {oid}",
                evidence_status="verified", page_start=1, category="other", penalty_text=None, cross_refs=[],
                actor="Velloran Components LLP", action="act", object=None)
    return NS(**{**base, **kw})


OBLS = [o("O-001", "C03", "po_issued", "delivery"), o("O-002", "C05", "delivery", "acceptance"),
        o("O-003", "C09", "invoice_receipt", "payment"),
        o("O-004", "C12", None, None, category="penalty", penalty_text="liquidated damages of 0.5% per week")]


def keyset(edges):
    return {(e.upstream_id, e.downstream_id, e.relation, e.source) for e in edges}


def test_rule_edges_event_chain_crossref_and_penalty():
    doc, clauses, pages = _doc()
    edges = rule_edges(CID, OBLS, clauses, pages)
    assert keyset(edges) == {("O-001", "O-002", "must_precede", "rule"),
                             ("O-001", "O-002", "depends_on", "rule"),
                             ("O-001", "O-004", "may_trigger", "rule")}
    chain = next(e for e in edges if e.relation == "must_precede")
    assert chain.evidence_quote == "raw O-002" and chain.rationale.startswith("O-001 produces 'delivery'")
    xref = next(e for e in edges if e.relation == "depends_on")
    assert xref.evidence_quote.startswith("Subject to Section 3.1") and xref.evidence_quote in doc
    pen = next(e for e in edges if e.relation == "may_trigger")
    assert "fails to deliver under Section 3.1" in pen.evidence_quote and pen.evidence_quote in doc
    assert all(e.status == "proposed" for e in edges)


def test_rejected_obligations_get_no_rule_edges():
    doc, clauses, pages = _doc()
    obls = [o("O-001", "C03", "po_issued", "delivery", review_state="rejected"), OBLS[1]]
    assert rule_edges(CID, obls, clauses, pages) == []


def test_llm_edge_validation():
    doc, clauses, pages = _doc()
    props = [
        P2Edge(upstream_id="O-002", downstream_id="O-003", relation="must_precede", clause_id="C09",
               evidence_quote="Customer shall pay within thirty (30) days of receipt of a valid invoice",
               rationale="Payment follows inspection.", confidence=0.7),
        P2Edge(upstream_id="O-009", downstream_id="O-003", relation="depends_on", clause_id=None,
               evidence_quote="x" * 30, rationale=None, confidence=0.9),  # unknown ID
        P2Edge(upstream_id="O-003", downstream_id="O-003", relation="depends_on", clause_id=None,
               evidence_quote="x" * 30, rationale=None, confidence=0.9),  # self-loop
        P2Edge(upstream_id="O-001", downstream_id="O-003", relation="depends_on", clause_id=None,
               evidence_quote="Customer shall inspect the Goods within five (5) Business Days",  # in C05: not allowed
               rationale=None, confidence=0.6),
    ]
    edges, warnings = validate_llm_edges(CID, props, OBLS, clauses, doc, pages)
    assert len(edges) == 2 and "2 AI link proposal(s)" in warnings[0]
    ok, bad = edges
    assert (ok.evidence_status, ok.page, ok.source) == ("verified", 1, "llm")
    assert bad.evidence_status == "unverified" and bad.page is None

    obls = [OBLS[0], o("O-003", "C09", "invoice_receipt", "payment", cross_refs=["Section 5.1"])]
    edges, _ = validate_llm_edges(CID, [props[3]], obls, clauses, doc, pages)
    assert edges[0].evidence_status == "verified"  # C05 is allowed via O-003's cross-reference


def _e(up, down, rel="depends_on", source="llm", conf=0.5, status="proposed"):
    return Edge(contract_id=CID, upstream_id=up, downstream_id=down, relation=rel, source=source,
                confidence=conf, status=status, evidence_status="verified")


def test_cycle_breaking():
    edges = [_e("A", "B", source="rule", conf=None), _e("B", "C", conf=0.9), _e("C", "A", conf=0.4),
             _e("C", "D", conf=0.1), _e("D", "C", rel="may_trigger", conf=0.1)]
    assert break_cycles(edges) == 1
    assert [(e.upstream_id, e.downstream_id) for e in edges if e.status == "auto_rejected"] == [("C", "A")]
    assert edges[2].reject_reason == "cycle"
    rule_only = [_e("A", "B", source="rule"), _e("B", "A", source="rule")]
    assert break_cycles(rule_only) == 0 and all(e.status == "proposed" for e in rule_only)


def _client(transport):
    async def nosleep(_):
        return None
    return GeminiClient(Settings(gemini_rpm=6000, prompt_version=f"e-{uuid.uuid4()}"), transport=transport,
                        use_db_cache=False, sleep=nosleep)


async def test_build_edges_merges_llm_with_rules_rule_wins():
    doc, clauses, pages = _doc()

    async def p2(system, user, schema, api_key=""):
        assert "O-001 | Velloran Components LLP | act" in user and "<snippet" in user
        return RawResponse(json.dumps({"edges": [
            {"upstream_id": "O-001", "downstream_id": "O-002", "relation": "must_precede", "clause_id": "C05",
             "evidence_quote": "Customer shall inspect the Goods within five (5) Business Days of delivery",
             "rationale": "Inspection needs delivered goods.", "confidence": 0.8},
            {"upstream_id": "O-002", "downstream_id": "O-001", "relation": "depends_on", "clause_id": "C03",
             "evidence_quote": "Supplier shall deliver the Goods within ten (10) Business Days",
             "rationale": "bogus back-link", "confidence": 0.2},
            {"garbage": True}], "potential_conflicts": []}), "STOP")

    res = await build_edges(CID, OBLS, clauses, doc, pages, _client(p2), enable_llm=True)
    chain = next(e for e in res.edges if e.relation == "must_precede")
    assert chain.source == "rule" and "AI note: Inspection needs delivered goods." in chain.rationale
    back = next(e for e in res.edges if e.upstream_id == "O-002" and e.downstream_id == "O-001")
    assert back.status == "auto_rejected" and any("cycle" in w for w in res.warnings)


async def test_p2_failure_falls_back_to_rule_edges():
    doc, clauses, pages = _doc()

    async def down(system, user, schema, api_key=""):
        raise LLMUnavailable("503")

    res = await build_edges(CID, OBLS, clauses, doc, pages, _client(down), enable_llm=True)
    assert len(res.edges) == 3 and res.warnings == ["AI link proposals unavailable; showing rule-based links only."]
    off = await build_edges(CID, OBLS, clauses, doc, pages, None, enable_llm=False)
    assert len(off.edges) == 3 and off.warnings == []


def test_render_p2_is_compact_and_escaped():
    doc, clauses, _ = _doc()
    clauses[1].text += " Upon <b>acceptance</b> see Section 9."
    u = render_p2(OBLS, clauses)
    assert "O-002 | Velloran Components LLP | act |  | trigger: delivery | §5.1 | produces: acceptance" in u
    assert "<b>" not in u


def test_refresh_keeps_status_of_rule_edges_that_still_hold():
    keep = _e("A", "B", rel="must_precede", source="rule", status="confirmed")
    stale = _e("B", "C", rel="must_precede", source="rule")
    llm = _e("C", "D")
    fresh = [_e("A", "B", rel="must_precede", source="rule"), _e("A", "D", rel="must_precede", source="rule")]
    to_add, to_delete = refresh_rule_edges([keep, stale, llm], fresh)
    assert [(e.upstream_id, e.downstream_id) for e in to_add] == [("A", "D")]
    assert to_delete == [stale] and keep.status == "confirmed"


def test_edit_refreshes_rule_edges_via_api(seeded):  # noqa: F811
    client, cid, _ = seeded
    q = {"contract_id": cid, **AS_OF}
    a = client.patch("/api/obligations/O-002", params=q, json={"action": "confirm"}).json()
    chain = {(e["upstream_id"], e["downstream_id"]) for e in a["edges"] if e["relation"] == "must_precede"}
    assert chain == {("O-001", "O-002"), ("O-002", "O-003"), ("O-003", "O-004")}
    a = client.patch("/api/obligations/O-004", params=q,
                     json={"action": "edit", "patch": {"trigger_event": "payment"}}).json()
    chain = {(e["upstream_id"], e["downstream_id"]) for e in a["edges"] if e["relation"] == "must_precede"}
    assert ("O-003", "O-004") not in chain  # O-004 no longer waits on invoice_receipt
    assert by_id(a)["O-004"]["resolution_status"] == "unresolved_trigger"
