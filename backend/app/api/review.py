"""Human-in-the-loop mutations (TRD §7). Each one writes a review_actions audit row, recomputes
dates on the stored rows (no LLM), and returns the full updated Analysis.

Obligation IDs are unique only within a contract, so obligation routes take ?contract_id=.
"""

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.assemble import build_analysis, get_contract_or_404, resolve_as_of
from app.db import get_session
from app.models import Conflict, Edge, Event, Obligation, ReviewAction
from app.pipeline.recompute import recompute, refresh_rules
from app.pipeline.temporal import event_key
from app.schemas import (
    Analysis, ConflictReviewRequest, EdgeReviewRequest, EventDateRequest, ObligationReviewRequest,
    ObligationStatusRequest,
)

router = APIRouter(prefix="/api")


def _obligation(s: Session, contract_id: uuid.UUID, obligation_id: str) -> Obligation:
    get_contract_or_404(s, contract_id)
    o = s.get(Obligation, (contract_id, obligation_id))
    if o is None:
        raise HTTPException(status_code=404, detail="Obligation not found")
    return o


def _audit(s: Session, contract_id, target_type, target_id, action, before=None, after=None, note=None):
    s.add(ReviewAction(contract_id=contract_id, target_type=target_type, target_id=str(target_id), action=action,
                       before=before, after=after, note=note))


def _finish(s: Session, contract_id: uuid.UUID, as_of: dt.date | None, reviewed_only: bool) -> Analysis:
    recompute(s, contract_id)
    s.commit()
    contract = get_contract_or_404(s, contract_id)
    return build_analysis(s, contract, resolve_as_of(as_of), reviewed_only)


def _jsonable(v):
    return v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v


@router.patch("/obligations/{obligation_id}", response_model=Analysis)
def review_obligation(obligation_id: str, body: ObligationReviewRequest, contract_id: uuid.UUID,
                      as_of: dt.date | None = None, reviewed_only: bool = False,
                      s: Session = Depends(get_session)) -> Analysis:
    o = _obligation(s, contract_id, obligation_id)
    before_state = o.review_state
    if body.action == "confirm":
        o.review_state = "confirmed"
        _audit(s, contract_id, "obligation", o.id, "confirm", {"review_state": before_state},
               {"review_state": "confirmed"}, body.note)
    elif body.action == "reject":
        o.review_state = "rejected"
        _audit(s, contract_id, "obligation", o.id, "reject", {"review_state": before_state},
               {"review_state": "rejected"}, body.note)
    else:
        if body.patch is None:
            raise HTTPException(status_code=422, detail="edit needs a patch")
        changes = body.patch.model_dump(mode="json", exclude_unset=True)
        before, after = {}, {}
        prov = dict(o.field_provenance or {})
        for field, value in changes.items():
            old = getattr(o, field)
            if old == value:
                continue
            before[field], after[field] = _jsonable(old), value
            setattr(o, field, value)
            prov[field] = "user"
            if field == "trigger_event":  # keep the rule's anchor in step with the edited trigger
                o.deadline_rule = {**(o.deadline_rule or {}), "anchor_event": value}
        o.field_provenance = prov
        o.review_state = "edited"
        _audit(s, contract_id, "obligation", o.id, "edit", before, after, body.note)
    s.add(o)
    refresh_rules(s, contract_id)
    return _finish(s, contract_id, as_of, reviewed_only)


@router.patch("/obligations/{obligation_id}/status", response_model=Analysis)
def set_obligation_status(obligation_id: str, body: ObligationStatusRequest, contract_id: uuid.UUID,
                          as_of: dt.date | None = None, reviewed_only: bool = False,
                          s: Session = Depends(get_session)) -> Analysis:
    o = _obligation(s, contract_id, obligation_id)
    before = {"status": o.status, "completed_on": _jsonable(o.completed_on)}
    produced = event_key(o.id, o.produces_event) if o.produces_event != "other" else None
    ev = s.get(Event, (contract_id, produced)) if produced else None

    if body.status == "done":
        occurred = body.occurred_on or resolve_as_of(as_of)
        o.status, o.completed_on = "done", occurred
        other_completion = (ev is not None and ev.date_source == "completion"
                            and ev.source_obligation_id not in (None, o.id))
        if ev is not None and o.review_state != "rejected" and not other_completion:
            # completion cascade: this obligation's event now has a date. A rejected (not real) duty never
            # re-dates real ones, and a date set by another obligation's completion is not overwritten.
            _audit(s, contract_id, "event", ev.key, "completion",
                   {"date": _jsonable(ev.date), "date_source": ev.date_source},
                   {"date": occurred.isoformat(), "date_source": "completion"})
            ev.date, ev.date_source, ev.source_obligation_id = occurred, "completion", o.id
            s.add(ev)
    else:
        if o.status == "done" and ev is not None and ev.date_source == "completion" \
                and ev.source_obligation_id == o.id:
            ev.date, ev.date_source = None, None  # undoing completion un-sets the date it produced
            s.add(ev)
        o.status, o.completed_on = body.status, None
    _audit(s, contract_id, "obligation", o.id, "status", before,
           {"status": o.status, "completed_on": _jsonable(o.completed_on)})
    s.add(o)
    return _finish(s, contract_id, as_of, reviewed_only)


@router.patch("/edges/{edge_id}", response_model=Analysis)
def review_edge(edge_id: uuid.UUID, body: EdgeReviewRequest, as_of: dt.date | None = None,
                reviewed_only: bool = False, s: Session = Depends(get_session)) -> Analysis:
    e = s.get(Edge, edge_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Edge not found")
    before = e.status
    e.status = "confirmed" if body.action == "confirm" else "rejected"
    if e.status == "rejected":
        e.reject_reason = "reviewer"
    _audit(s, e.contract_id, "edge", e.id, body.action, {"status": before}, {"status": e.status}, body.note)
    s.add(e)
    return _finish(s, e.contract_id, as_of, reviewed_only)


@router.patch("/conflicts/{conflict_id}", response_model=Analysis)
def review_conflict(conflict_id: uuid.UUID, body: ConflictReviewRequest, as_of: dt.date | None = None,
                    reviewed_only: bool = False, s: Session = Depends(get_session)) -> Analysis:
    c = s.get(Conflict, conflict_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    before = c.status
    c.status = "dismissed" if body.action == "dismiss" else "open"
    _audit(s, c.contract_id, "conflict", c.id, body.action, {"status": before}, {"status": c.status}, body.note)
    s.add(c)
    return _finish(s, c.contract_id, as_of, reviewed_only)


@router.put("/contracts/{contract_id}/events/{key}", response_model=Analysis)
def set_event_date(contract_id: uuid.UUID, key: str, body: EventDateRequest, as_of: dt.date | None = None,
                   reviewed_only: bool = False, s: Session = Depends(get_session)) -> Analysis:
    get_contract_or_404(s, contract_id)
    ev = s.get(Event, (contract_id, key))
    if ev is None:
        raise HTTPException(status_code=404, detail="Event not found")
    before = {"date": _jsonable(ev.date), "date_source": ev.date_source}
    ev.date, ev.date_source = body.date, ("user" if body.date else None)
    _audit(s, contract_id, "event", key, "set_date" if body.date else "clear_date", before,
           {"date": _jsonable(body.date), "date_source": ev.date_source})
    s.add(ev)
    return _finish(s, contract_id, as_of, reviewed_only)
