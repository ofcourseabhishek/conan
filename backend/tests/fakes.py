"""A deterministic stand-in for Gemini P1: one obligation per 'shall/may' sentence, quoted verbatim
from the clause, with the actor taken from the sentence's first party role word."""

import json
import re

from app.pipeline.gemini import RawResponse

_CLAUSE = re.compile(r'<clause id="(C\d+)" ref="[^"]*">(.*?)</clause>', re.S)
_SENT = re.compile(r"[^.]*\b(shall|may)\b[^.]*\.", re.S)


async def fake_p1(system: str, user: str, schema) -> RawResponse:
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
