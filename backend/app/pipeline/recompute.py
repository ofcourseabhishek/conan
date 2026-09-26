"""Recompute after any change (TRD §2, §10): events sync + temporal resolution on stored rows.
Synchronous, no LLM call. Risk is computed on read, so it needs no step here. Callers commit.
"""

from __future__ import annotations

import uuid

from sqlmodel import Session, select

from app.models import Clause, Edge, Event, Obligation, Page
from app.pipeline.edges import refresh_rule_edges, rule_edges
from app.pipeline.temporal import EventDate, event_key, event_label, resolve


def sync_events(s: Session, contract_id: uuid.UUID, obligations: list[Obligation]) -> dict[str, Event]:
    """Ensure an Event row exists for every anchor and produced event. Dates are never touched here."""
    events = {e.key: e for e in s.exec(select(Event).where(Event.contract_id == contract_id)).all()}
    for o in sorted(obligations, key=lambda o: o.id):
        anchor = (o.deadline_rule or {}).get("anchor_event") or o.trigger_event
        for ev, produced in ((anchor, False), (o.produces_event, True)):
            key = event_key(o.id, ev)
            if key is None or (produced and ev == "other"):
                continue  # an 'other' produced event can't be matched to anything
            row = events.get(key)
            if row is None:
                row = Event(contract_id=contract_id, key=key, label=event_label(ev, o.trigger_label))
                events[key] = row
                s.add(row)
            if produced and row.source_obligation_id is None:
                row.source_obligation_id = o.id
                s.add(row)
    return events


def recompute(s: Session, contract_id: uuid.UUID) -> None:
    obligations = s.exec(select(Obligation).where(Obligation.contract_id == contract_id)).all()
    events = sync_events(s, contract_id, obligations)
    dated = {k: EventDate(e.date, e.date_source) for k, e in events.items() if e.date is not None}
    for o in obligations:
        r = resolve(o, dated)
        o.due_date, o.resolution_status, o.resolution_trace = r.due_date, r.status, r.trace
        o.date_provenance = r.provenance
        o.next_occurrences = [d.isoformat() for d in r.next_occurrences]
        s.add(o)
    s.flush()


def refresh_rules(s: Session, contract_id: uuid.UUID) -> None:
    """Re-derive rule edges after a reviewer changes an obligation (trigger, produced event, reject).
    Rule edges that still hold keep their review status; LLM edges are left alone."""
    s.flush()
    obligations = s.exec(select(Obligation).where(Obligation.contract_id == contract_id)).all()
    clauses = s.exec(select(Clause).where(Clause.contract_id == contract_id)).all()
    pages = s.exec(select(Page).where(Page.contract_id == contract_id).order_by(Page.page_no)).all()
    existing = s.exec(select(Edge).where(Edge.contract_id == contract_id)).all()
    fresh = rule_edges(contract_id, obligations, clauses, [(p.char_start, p.char_end) for p in pages])
    to_add, to_delete = refresh_rule_edges(existing, fresh)
    for e in to_delete:
        s.delete(e)
    s.add_all(to_add)
    s.flush()
