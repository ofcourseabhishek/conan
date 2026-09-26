"""DB rows -> the single `Analysis` payload (TRD §7). Pure read; risk is computed on read."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlmodel import Session, select

from app.config import get_settings
from app.models import Clause, Conflict, Contract, Edge, Event, Obligation, ReviewAction
from app.pipeline.risk import edge_propagates, score_all
from app.pipeline.runner import latest_job
from app.schemas import (
    Analysis, ClauseOut, ConflictOut, ContractOut, EdgeOut, EventOut, ObligationOut, Party, ReviewActionOut, Stats,
)

NEEDS_REVIEW_BELOW = 0.6


def needs_review(o: Obligation) -> bool:
    return o.review_state == "proposed" and (o.evidence_status != "verified" or o.confidence < NEEDS_REVIEW_BELOW)


def resolve_as_of(as_of: dt.date | None) -> dt.date:
    if as_of:
        return as_of
    demo = get_settings().demo_as_of
    return dt.date.fromisoformat(demo) if demo else dt.date.today()


def build_analysis(s: Session, contract: Contract, as_of: dt.date, reviewed_only: bool) -> Analysis:
    cid = contract.id
    clauses = s.exec(select(Clause).where(Clause.contract_id == cid).order_by(Clause.char_start)).all()
    obligations = s.exec(select(Obligation).where(Obligation.contract_id == cid).order_by(Obligation.id)).all()
    edges = s.exec(select(Edge).where(Edge.contract_id == cid)).all()
    events = s.exec(select(Event).where(Event.contract_id == cid)).all()
    conflicts = s.exec(select(Conflict).where(Conflict.contract_id == cid)).all()
    actions = s.exec(select(ReviewAction).where(ReviewAction.contract_id == cid).order_by(ReviewAction.at)).all()

    risks = score_all(obligations, edges, conflicts, as_of, reviewed_only)
    obligation_out = [ObligationOut.model_validate({**o.model_dump(), "risk": risks[o.id],
                                                   "needs_review": needs_review(o)}) for o in obligations]
    edge_out = [EdgeOut.model_validate({**e.model_dump(), "propagates": edge_propagates(e, reviewed_only)})
                for e in edges]

    with_obl = {o.clause_id for o in obligations}
    job = latest_job(s, cid)
    warnings = list(job.warnings) if job else []
    return Analysis(
        contract=ContractOut(
            id=cid, name=contract.name, filename=contract.filename,
            parties=[Party(**p) for p in contract.parties or []], page_count=contract.page_count,
            is_sample=contract.is_sample, cached_at=contract.cached_at,
            pipeline_version=contract.pipeline_version, created_at=contract.created_at,
        ),
        as_of=as_of, reviewed_only=reviewed_only,
        clauses=[ClauseOut.model_validate(c, from_attributes=True) for c in clauses],
        obligations=obligation_out,
        edges=edge_out,
        events=[EventOut(key=e.key, label=e.label, date=e.date, date_source=e.date_source,
                         source_obligation_id=e.source_obligation_id,
                         dependent_obligation_ids=sorted(o.id for o in obligations
                                                         if (o.deadline_rule or {}).get("anchor_event") == e.key))
                for e in events],
        conflicts=[ConflictOut.model_validate(c, from_attributes=True) for c in conflicts],
        review_actions=[ReviewActionOut.model_validate(a, from_attributes=True) for a in actions],
        stats=Stats(
            clauses=len(clauses), obligations=len(obligation_out),
            unresolved_dates=sum(o.resolution_status == "unresolved_trigger" for o in obligations),
            needs_review=sum(o.needs_review for o in obligation_out),
            clauses_without_obligations=sum(c.id not in with_obl for c in clauses),
            warnings=warnings,
        ),
    )


def get_contract_or_404(s: Session, contract_id: uuid.UUID) -> Contract:
    from fastapi import HTTPException

    c = s.get(Contract, contract_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return c
