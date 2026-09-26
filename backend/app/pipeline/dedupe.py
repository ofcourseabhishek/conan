"""Stage 4: verify evidence, canonicalize actors, dedupe, assign IDs, build obligation rows
(TRD §5.4, §9.1). The server assigns O-001... in document order, after dedupe.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.models import Obligation
from app.pipeline.llm_schemas import P1Obligation
from app.pipeline.verify import Match, clause_at, page_of, verify_quote

UNVERIFIED_CAP = 0.4
_MUTUAL = re.compile(r"^(either|each|both|any)\s+part(y|ies)$", re.I)
_RAW_DEADLINE = re.compile(
    r"\b(within|no later than|not later than|at least|prior to|before|after|following|upon|by)\b[^.;]*", re.I)


@dataclass
class ClauseRef:
    id: str
    char_start: int
    char_end: int
    page_start: int


@dataclass
class Candidate:
    item: P1Obligation
    clause_id: str
    actor: str
    actor_known: bool
    match: Match
    page_start: int
    page_end: int
    page_approx: bool
    confidence: float


def canonical_party(name: str | None, parties: list[dict]) -> tuple[str | None, bool]:
    """Map an LLM actor string to a party name from segmentation. Returns (name, known)."""
    if not name:
        return name, False
    low = name.strip().casefold()
    for p in parties:
        if low in (p["name"].casefold(), (p.get("role") or "").casefold()):
            return p["name"], True
    best = max(parties, key=lambda p: fuzz.token_set_ratio(low, p["name"].casefold()), default=None)
    if best and fuzz.token_set_ratio(low, best["name"].casefold()) >= 85:
        return best["name"], True
    if _MUTUAL.match(name.strip()):
        return name.strip(), True
    return name.strip(), not parties  # no parties detected: can't judge, don't penalize


def displayed_confidence(llm_conf: float, evidence_score: int, item: P1Obligation, verified: bool,
                         actor_known: bool) -> float:
    completeness = sum(v is not None for v in (item.actor, item.action, item.object, item.deadline_kind)) / 4
    conf = 0.5 * llm_conf + 0.3 * (evidence_score / 100) + 0.2 * completeness
    if not verified or not actor_known:
        conf = min(conf, UNVERIFIED_CAP)
    return round(conf, 2)


def verify_all(items: list[P1Obligation], clauses: list[ClauseRef], doc_text: str,
               page_offsets: list[tuple[int, int]], parties: list[dict]) -> list[Candidate]:
    by_id = {c.id: c for c in clauses}
    spans = [(c.id, c.char_start, c.char_end) for c in clauses]
    out = []
    for it in items:
        clause = by_id[it.clause_id]
        m = verify_quote(it.evidence_quote, doc_text, (clause.char_start, clause.char_end), page_offsets)
        cid = it.clause_id
        if m.status == "verified":
            cid = clause_at(spans, m.start) or cid  # quote found in another clause: reassign
            p0, p1, approx = page_of(page_offsets, m.start), page_of(page_offsets, m.end - 1), False
        else:
            p0 = p1 = clause.page_start
            approx = True
        actor, known = canonical_party(it.actor, parties)
        cp, _ = canonical_party(it.counterparty, parties)
        it.counterparty = cp
        conf = displayed_confidence(it.confidence, m.score if m.status == "verified" else 0, it,
                                    m.status == "verified", known)
        out.append(Candidate(it, cid, actor, known, m, p0, p1, approx, conf))
    return out


def _overlap(a: Candidate, b: Candidate) -> float:
    if a.match.start is None or b.match.start is None:
        return 0.0
    inter = min(a.match.end, b.match.end) - max(a.match.start, b.match.start)
    shorter = min(a.match.end - a.match.start, b.match.end - b.match.start)
    return max(0, inter) / shorter if shorter else 0.0


def _same(a: Candidate, b: Candidate) -> bool:
    if a.clause_id != b.clause_id or a.actor.casefold() != b.actor.casefold():
        return False
    ao = f"{a.item.action} {a.item.object or ''}".casefold()
    bo = f"{b.item.action} {b.item.object or ''}".casefold()
    return _overlap(a, b) >= 0.6 or fuzz.token_set_ratio(ao, bo) >= 90


def dedupe(cands: list[Candidate]) -> list[Candidate]:
    kept: list[Candidate] = []
    for c in sorted(cands, key=lambda c: -c.confidence):
        dup = next((k for k in kept if _same(k, c)), None)
        if dup is None:
            kept.append(c)
            continue
        for f, v in c.item.model_dump().items():  # fill nulls on the keeper from the loser
            if getattr(dup.item, f) in (None, []) and v not in (None, []):
                setattr(dup.item, f, v)
    return kept


def _provisional_resolution(kind: str, is_conditional: bool, anchor: str | None) -> str:
    """Stage 5 (temporal) refines this; until an anchor event has a date nothing is resolved."""
    if is_conditional:
        return "conditional_pending"
    if kind == "none":
        return "no_deadline"
    if kind in ("relative", "recurring"):
        return "unresolved_trigger" if anchor else "ambiguous"
    return "ambiguous"  # absolute: parsed against the verified quote in stage 5


def _anchor(it: P1Obligation) -> str | None:
    """A period-end schedule starts at the effective date unless a real start event was named; models tend
    to call the period end itself 'other', which nobody could ever set a date for."""
    if it.deadline_kind == "recurring" and it.recurrence_basis == "period_end"             and it.trigger_event in (None, "other"):
        return "effective_date"
    return it.trigger_event


def deadline_rule(it: P1Obligation) -> dict:
    offset = None
    if it.offset_value is not None and it.offset_unit:
        offset = {"value": it.offset_value, "unit": it.offset_unit, "day_type": it.day_type or "unspecified"}
    m = _RAW_DEADLINE.search(it.evidence_quote)
    return {
        "kind": it.deadline_kind,
        "raw_text": m.group(0).strip() if m and it.deadline_kind != "none" else None,
        "absolute_date_text": it.absolute_date_text,
        "absolute_date": None,
        "offset": offset,
        "direction": it.direction,
        "anchor_event": _anchor(it),
        "recurrence": it.recurrence_freq,
        "recurrence_basis": it.recurrence_basis,
        "is_conditional": it.is_conditional,
    }


EXTRACTED_FIELDS = ("actor", "counterparty", "modality", "action", "object", "category", "trigger_event",
                    "produces_event", "is_conditional", "deadline_rule", "amount", "penalty_text", "cross_refs")


def build_rows(contract_id: uuid.UUID, cands: list[Candidate], clause_start: dict[str, int]) -> list[Obligation]:
    ordered = sorted(cands, key=lambda c: (c.match.start if c.match.start is not None else clause_start[c.clause_id],
                                           c.actor, c.item.action))
    rows = []
    for n, c in enumerate(ordered, start=1):
        it = c.item
        rule = deadline_rule(it)
        rows.append(Obligation(
            contract_id=contract_id, id=f"O-{n:03d}", clause_id=c.clause_id,
            actor=c.actor, counterparty=it.counterparty, modality=it.modality, action=it.action, object=it.object,
            category=it.category, trigger_event=it.trigger_event, trigger_label=it.trigger_label,
            produces_event=it.produces_event, is_conditional=it.is_conditional, condition_text=it.condition_text,
            deadline_rule=rule,
            amount={"value": it.amount_value, "currency": it.amount_currency} if it.amount_value is not None else None,
            penalty_text=it.penalty_text, cross_refs=it.cross_refs, evidence_quote=it.evidence_quote,
            evidence_start=c.match.start, evidence_end=c.match.end, evidence_status=c.match.status,
            evidence_score=c.match.score if c.match.status == "verified" else None,
            page_start=c.page_start, page_end=c.page_end, page_approx=c.page_approx,
            llm_confidence=it.confidence, confidence=c.confidence,
            resolution_status=_provisional_resolution(it.deadline_kind, it.is_conditional, it.trigger_event),
            field_provenance={**{f: "extracted" for f in EXTRACTED_FIELDS},
                              "due_date": "computed", "confidence": "computed", "page": "computed"},
        ))
    return rows
