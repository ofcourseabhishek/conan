"""A deterministic stand-in for Gemini P1: one obligation per 'shall/may' sentence, quoted verbatim
from the clause, with the actor taken from the sentence's first party role word."""

import json
import re

from app.pipeline.gemini import RawResponse

_CLAUSE = re.compile(r'<clause id="(C\d+)" ref="[^"]*">(.*?)</clause>', re.S)
_SENT = re.compile(r"[^.]*\b(shall|may)\b[^.]*\.", re.S)


async def fake_p1(system: str, user: str, schema, api_key: str = "") -> RawResponse:
    clauses, obligations = [], []
    for cid, text in _CLAUSE.findall(user):
        clauses.append({"clause_id": cid, "category": "other"})
        for m in _SENT.finditer(text):
            sent = " ".join(m.group(0).split())
            actor = next((w for w in re.findall(r"\b(Customer|Supplier)\b", sent)), None)
            if not actor or len(sent) < 25:
                continue
            obligations.append({
                "clause_id": cid, "actor": actor, "counterparty": None,
                "modality": "may" if m.group(1) == "may" else "must",
                "action": sent.split(m.group(1), 1)[1].split()[0], "object": None, "category": "other",
                "trigger_event": None, "trigger_label": None, "produces_event": None, "is_conditional": False,
                "condition_text": None, "deadline_kind": "none", "absolute_date_text": None, "offset_value": None,
                "offset_unit": None, "day_type": None, "direction": None, "recurrence_freq": None,
                "amount_value": None, "amount_currency": None, "penalty_text": None, "cross_refs": [],
                "evidence_quote": sent[:300], "confidence": 0.8,
            })
    return RawResponse(json.dumps({"clauses": clauses, "obligations": obligations}), "STOP")


def _p1_item(clause_id, actor, action, obj, category, trig, prod, kind, quote, value=None, day_type=None,
             modality="must", **kw):
    item = {"clause_id": clause_id, "actor": actor, "counterparty": None, "modality": modality, "action": action,
            "object": obj, "category": category, "trigger_event": trig, "trigger_label": None,
            "produces_event": prod, "is_conditional": False, "condition_text": None, "deadline_kind": kind,
            "absolute_date_text": None, "offset_value": value, "offset_unit": "day" if value else None,
            "day_type": day_type, "direction": "after" if value else None, "recurrence_freq": None,
            "amount_value": None, "amount_currency": None, "penalty_text": None, "cross_refs": [],
            "evidence_quote": quote, "confidence": 0.9}
    item.update(kw)
    return item


# keyed by text that identifies the clause in the synthetic contract (tests/pdfgen.py)
_DEMO_P1 = {
    "3.1 Delivery": ("Supplier", "deliver", "Goods", "delivery", "po_issued", "delivery", "relative",
                     "Supplier shall deliver the Goods specified in each Purchase Order to the Customer's Pune "
                     "facility within ten (10) Business Days of the issuance of such Purchase Order", 10, "business"),
    "5.1 Inspection": ("Customer", "inspect", "Goods", "delivery", "delivery", "acceptance", "relative",
                       "Customer shall inspect the Goods within five (5) Business Days of delivery", 5, "business"),
    "6.2 Invoicing": ("Supplier", "invoice", "Customer", "payment", "acceptance", "invoice_receipt", "none",
                      "Upon Acceptance, Supplier may invoice Customer for the Goods", None, None),
    "6.3 Payment": ("Customer", "pay", "undisputed amounts", "payment", "invoice_receipt", "payment", "relative",
                    "Customer shall pay all undisputed amounts within thirty (30) days of receipt of a valid invoice",
                    30, "calendar"),
}


async def demo_llm(system: str, user: str, schema, api_key: str = "") -> RawResponse:
    """Scripted P1 + P2 for the synthetic contract, shaped like good model output."""
    if user.startswith("OBLIGATIONS"):
        ids = {line.split(" | ")[2]: line.split(" | ")[0] for line in user.splitlines() if " | " in line}
        edges = []
        if "inspect" in ids and "invoice" in ids:
            edges.append({"upstream_id": ids["inspect"], "downstream_id": ids["invoice"], "relation": "condition_for",
                          "evidence_quote": "Upon Acceptance, Supplier may invoice Customer for the Goods",
                          "clause_id": None, "rationale": "Invoicing is allowed only after acceptance.",
                          "confidence": 0.8})
        return RawResponse(json.dumps({"edges": edges, "potential_conflicts": []}), "STOP")
    clauses, obligations = [], []
    for cid, text in _CLAUSE.findall(user):
        for key, spec in _DEMO_P1.items():
            if key in text:
                actor, action, obj, cat, trig, prod, kind, quote, value, day_type = spec
                clauses.append({"clause_id": cid, "category": cat})
                obligations.append(_p1_item(cid, actor, action, obj, cat, trig, prod, kind, quote, value, day_type,
                                            modality="may" if action == "invoice" else "must"))
    return RawResponse(json.dumps({"clauses": clauses, "obligations": obligations}), "STOP")
