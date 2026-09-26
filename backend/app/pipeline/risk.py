"""Attention priority, 0-100 (TRD §9.5). Pure function of stored rows + as_of; computed on read.

Additive capped points, one visible row per factor. Propagation (D1) starts from the *state* of
upstream obligations (blocked/overdue = 1.0, unresolved must = 0.5), never their scores, and takes
the max over paths, so risk never compounds and unrelated obligations never move each other.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from app.pipeline.temporal import upcoming_due
from app.schemas import PathStep, Risk, RiskFactor

W = {"condition_for": 1.0, "depends_on": 1.0, "must_precede": 0.8, "may_trigger": 0.6}
HOP_DECAY, MAX_HOPS, IMPACT_CAP, BASE = 0.6, 3, 30, 30
CAT_HIGH = {"payment", "termination", "penalty"}
CAT_MED = {"renewal", "compliance", "delivery"}


def band(score: int) -> str:
    return "low" if score < 25 else "medium" if score < 50 else "high" if score < 75 else "critical"


def _r(x: float) -> int:
    return int(x + 0.5)


def is_active(o) -> bool:
    return o.status not in ("done", "waived") and o.review_state != "rejected"


def is_overdue(o, as_of: dt.date) -> bool:
    due = upcoming_due(o, as_of)
    return is_active(o) and due is not None and due < as_of and o.resolution_status != "conditional_pending"


def is_unresolved_must(o) -> bool:
    return o.modality == "must" and o.resolution_status in ("unresolved_trigger", "ambiguous")


def edge_propagates(e, reviewed_only: bool) -> bool:
    if e.status == "confirmed":
        return True
    return not reviewed_only and e.status == "proposed" and e.evidence_status == "verified"


@dataclass
class _Best:
    value: float
    source: str
    s: float
    path: list


def _impacts(obls: dict, edges: list, as_of: dt.date, reviewed_only: bool) -> dict[str, _Best]:
    out_edges = defaultdict(list)
    for e in edges:
        if edge_propagates(e, reviewed_only) and e.upstream_id in obls and e.downstream_id in obls:
            out_edges[e.upstream_id].append(e)
    best: dict[str, _Best] = {}
    for oid, o in obls.items():
        if not is_active(o):
            continue
        s = 1.0 if (o.status == "blocked" or is_overdue(o, as_of)) else 0.5 if is_unresolved_must(o) else 0.0
        if not s:
            continue
        stack = [(oid, 1.0, [], {oid})]
        while stack:
            node, prod, path, seen = stack.pop()
            if len(path) >= MAX_HOPS:
                continue
            for e in out_edges[node]:
                nxt = e.downstream_id
                if nxt in seen or not is_active(obls[nxt]):
                    continue  # a done, waived or rejected obligation breaks the chain
                p = prod * W[e.relation]
                hop = len(path) + 1
                val = BASE * s * p * HOP_DECAY ** (hop - 1)
                new_path = path + [e]
                if nxt not in best or val > best[nxt].value:
                    best[nxt] = _Best(val, oid, s, new_path)
                stack.append((nxt, p, new_path, seen | {nxt}))
    return best


def score_all(obligations: list, edges: list, conflicts: list, as_of: dt.date,
              reviewed_only: bool = False) -> dict[str, Risk]:
    obls = {o.id: o for o in obligations}
    in_conflict = {oid for c in conflicts if c.status == "open" for oid in c.obligation_ids}
    impacts = _impacts(obls, edges, as_of, reviewed_only)
    out: dict[str, Risk] = {}
    for oid, o in obls.items():
        if not is_active(o):
            out[oid] = Risk(score=0, band="low", factors=[])
            continue
        f: list[RiskFactor] = []
        time_mult = 0.0 if o.resolution_status == "conditional_pending" else 0.5 if o.modality in ("may", "must_not") else 1.0
        due = upcoming_due(o, as_of)
        if due is not None and time_mult:
            days = (due - as_of).days
            note = "" if time_mult == 1 else f" (×0.5 for '{o.modality}')"
            if days < 0:
                f.append(RiskFactor(factor="Overdue", points=_r(35 * time_mult), provenance="computed",
                                    detail=f"Due {due}, {-days} days before {as_of}{note}"))
            elif days <= 7:
                f.append(RiskFactor(factor="Due within 7 days", points=_r(20 * time_mult), provenance="computed",
                                    detail=f"Due {due}, {days} days after {as_of}{note}"))
            elif days <= 30:
                f.append(RiskFactor(factor="Due in 8-30 days", points=_r(10 * time_mult), provenance="computed",
                                    detail=f"Due {due}, {days} days after {as_of}{note}"))
        if o.status == "blocked":
            f.append(RiskFactor(factor="Status blocked", points=30, provenance="user"))
        if o.penalty_text:
            f.append(RiskFactor(factor="Explicit penalty / consequence", points=15, provenance="extracted",
                                detail=o.penalty_text))
        if o.amount:
            f.append(RiskFactor(factor="Monetary amount stated", points=5, provenance="extracted",
                                detail=f"{o.amount.get('currency') or ''} {o.amount.get('value'):,.0f}".strip()))
        if o.category in CAT_HIGH:
            f.append(RiskFactor(factor=f"Category {o.category}", points=10, provenance="extracted"))
        elif o.category in CAT_MED:
            f.append(RiskFactor(factor=f"Category {o.category}", points=7, provenance="extracted"))
        if is_unresolved_must(o):
            anchor = (o.deadline_rule or {}).get("anchor_event")
            f.append(RiskFactor(factor="Unresolved date on a must", points=8, provenance="computed",
                                detail=f"Needs the '{anchor}' date" if anchor else "Deadline could not be read"))
        off = (o.deadline_rule or {}).get("offset") or {}
        if off.get("day_type") == "unspecified" and off.get("value"):  # a 0-day gap has no day type
            f.append(RiskFactor(factor="Day type unspecified", points=5, provenance="computed",
                                detail="Counted as calendar days"))
        if o.evidence_status != "verified":
            f.append(RiskFactor(factor="Evidence unverified", points=10, provenance="computed"))
        if o.confidence < 0.6:
            f.append(RiskFactor(factor="Confidence below 0.6", points=7, provenance="computed",
                                detail=f"Confidence {o.confidence:.2f}"))
        if oid in in_conflict:
            f.append(RiskFactor(factor="Part of a flagged conflict", points=12, provenance="computed"))
        if (b := impacts.get(oid)) and (pts := _r(min(IMPACT_CAP, b.value))) > 0:
            src = obls[b.source]
            state = "blocked" if src.status == "blocked" else "overdue" if is_overdue(src, as_of) else "waiting on a date"
            terms = " × ".join(f"{e.relation} {W[e.relation]}" for e in b.path)
            decay = f" × {HOP_DECAY}^{len(b.path) - 1}" if len(b.path) > 1 else ""
            f.append(RiskFactor(
                factor="Potential downstream impact", points=pts, provenance="computed",
                detail=f"{b.source} is {state}: 30 × {b.s} × {terms}{decay} = {b.value:.1f}",
                path=[PathStep(edge_id=e.id, upstream_id=e.upstream_id, downstream_id=e.downstream_id,
                               relation=e.relation, quote=e.evidence_quote, page=e.page) for e in b.path]))
        score = min(100, sum(x.points for x in f))
        out[oid] = Risk(score=score, band=band(score), factors=f)
    return out
