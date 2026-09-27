"""Stage 5: deadline resolution (TRD §9.2). Pure functions; no invented dates.

Every non-null due_date gets date_provenance in {contract_text, user_event, completion}:
  contract_text  an absolute date whose literal text sits inside the VERIFIED evidence quote
  user_event     computed from an event date a person typed (or a date a reviewer entered)
  completion     computed from the date a person marked the producing obligation done
Relative deadlines stay `unresolved_trigger` until their anchor event has a date.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from dateutil import parser as dparser
from dateutil.relativedelta import relativedelta

EVENT_LABELS = {
    "effective_date": "Effective date", "po_issued": "Purchase order issued", "delivery": "Goods delivered",
    "inspection_complete": "Inspection complete", "acceptance": "Goods accepted",
    "certificate_submitted": "Certificate submitted", "invoice_receipt": "Invoice received",
    "payment": "Payment made", "notice_given": "Notice given", "term_start": "Term starts",
    "term_end": "Term ends", "renewal": "Renewal", "termination": "Termination",
}
_PROVENANCE = {"user": "user_event", "completion": "completion", "contract_text": "contract_text"}
_SOURCE_WORD = {"user": "user-set", "completion": "marked done", "contract_text": "from the contract"}
_FREQ = {"weekly": relativedelta(weeks=1), "monthly": relativedelta(months=1),
         "quarterly": relativedelta(months=3), "annually": relativedelta(years=1)}
# About a year of occurrences, so the "next upcoming" one exists for a while after the start date.
OCCURRENCES = {"weekly": 8, "monthly": 12, "quarterly": 4, "annually": 3}
_PERIOD = {"weekly": "week", "monthly": "month", "quarterly": "quarter", "annually": "year"}


@dataclass
class EventDate:
    date: dt.date
    source: str  # user | completion | contract_text


@dataclass
class Resolution:
    status: str
    due_date: dt.date | None = None
    provenance: str | None = None
    trace: str | None = None
    next_occurrences: list[dt.date] = field(default_factory=list)


# Too generic to share: one contract has delay notices, defect notices, renewal notices and termination
# notices, and merging them re-dates unrelated deadlines (eval run #1 on the demo contract). Like 'other',
# these are keyed per obligation and never chained by the rule edges.
PER_OBLIGATION_EVENTS = {"other", "notice_given"}


def is_per_obligation(event: str | None) -> bool:
    return event in PER_OBLIGATION_EVENTS


def event_key(obligation_id: str, event: str | None) -> str | None:
    """Per-obligation events ('other', 'notice_given') never merge automatically."""
    if not event:
        return None
    return f"{event}:{obligation_id}" if is_per_obligation(event) else event


def event_label(event: str, trigger_label: str | None, obligation_id: str | None = None) -> str:
    if event == "other":
        return (trigger_label or "Other event")[:80]
    label = EVENT_LABELS.get(event, event)
    return f"{label} ({obligation_id})" if is_per_obligation(event) and obligation_id else label


def add_business_days(d: dt.date, n: int) -> dt.date:
    step = 1 if n >= 0 else -1
    left = abs(n)
    while left:
        d += dt.timedelta(days=step)
        if d.weekday() < 5:
            left -= 1
    return d


def apply_offset(anchor: dt.date, offset: dict, direction: str | None) -> tuple[dt.date, str]:
    n, unit, day_type = offset["value"], offset["unit"], offset.get("day_type") or "unspecified"
    sign = -1 if direction == "before" else 1
    if unit == "day" and day_type == "business":
        return add_business_days(anchor, sign * n), f"{n} business day{'s' * (n != 1)} (weekends skipped; holidays not considered)"
    if unit == "day":
        note = "calendar days (day type not stated; counted as calendar days)" if day_type == "unspecified" \
            else "calendar days"
        return anchor + dt.timedelta(days=sign * n), f"{n} {note}"
    if unit == "week":
        return anchor + dt.timedelta(weeks=sign * n), f"{n} week{'s' * (n != 1)}"
    delta = relativedelta(months=n) if unit == "month" else relativedelta(years=n)
    return (anchor - delta if sign < 0 else anchor + delta), f"{n} {unit}{'s' * (n != 1)} (month-end clamped)"


def _flat(s: str) -> str:
    return " ".join(s.split()).casefold()


def parse_literal_date(text: str) -> dt.date | None:
    """A fully specified date (day, month, year) or None. Day-first, as in Indian contracts."""
    try:
        a = dparser.parse(text, dayfirst=True, fuzzy=False, default=dt.datetime(1901, 1, 1))
        b = dparser.parse(text, dayfirst=True, fuzzy=False, default=dt.datetime(1902, 2, 2))
    except (ValueError, OverflowError):
        return None
    return a.date() if a == b else None  # differing results = some part was missing and defaulted


def resolve(o, events: dict[str, EventDate]) -> Resolution:
    rule = o.deadline_rule or {}
    kind = rule.get("kind", "none")
    fp = o.field_provenance or {}

    # A reviewer-entered absolute date is a date the user entered.
    if fp.get("deadline_rule") == "user" and rule.get("absolute_date"):
        d = _as_date(rule["absolute_date"])
        return Resolution("resolved", d, "user_event", f"{d} (entered by a reviewer)")

    if kind == "none":
        return Resolution("no_deadline")

    key = event_key(o.id, rule.get("anchor_event") or o.trigger_event)
    anchor = events.get(key) if key else None

    if (rule.get("is_conditional") or o.is_conditional) and anchor is None:
        return Resolution("conditional_pending", trace="Applies only if its condition occurs")

    if kind == "absolute":
        text = rule.get("absolute_date_text")
        if not text:
            return Resolution("ambiguous", trace="No date text was extracted")
        if o.evidence_status != "verified" or _flat(text) not in _flat(o.evidence_quote or ""):
            return Resolution("ambiguous", trace=f"'{text}' is not in the verified quote")
        d = parse_literal_date(text)
        if d is None:
            return Resolution("ambiguous", trace=f"'{text}' is not a complete date")
        return Resolution("resolved", d, "contract_text", f"'{text}' as written in the contract")

    if not key:
        return Resolution("ambiguous", trace="No trigger event identified")
    if anchor is None:
        return Resolution("unresolved_trigger", trace=f"Waiting for the '{key}' date")

    head = f"{key} ({anchor.date}, {_SOURCE_WORD[anchor.source]})"
    prov = _PROVENANCE[anchor.source]
    offset = rule.get("offset")

    if kind == "recurring" and not rule.get("recurrence") and offset and rule.get("recurrence_basis") != "period_end":
        # "within 15 days of each renewal": no fixed frequency, so it is due from the latest such event
        due, desc = apply_offset(anchor.date, offset, rule.get("direction"))
        sign = "−" if rule.get("direction") == "before" else "+"
        return Resolution("resolved", due, prov, f"{head} {sign} {desc} → {due} (repeats after each {key})")

    if kind == "recurring":
        name = rule.get("recurrence") or ""
        freq = _FREQ.get(name)
        if freq is None:
            return Resolution("ambiguous", trace="Recurrence frequency not identified")
        n, direction = OCCURRENCES[name], rule.get("direction") or "after"
        if rule.get("recurrence_basis") == "period_end":
            ends = period_ends(anchor.date, name, n)
            if offset and offset.get("value"):  # "by the last day of each quarter" has no gap at all
                occ = [apply_offset(e, offset, direction)[0] for e in ends]
                sign = "−" if direction == "before" else "+"
                gap = f" {sign} {apply_offset(ends[0], offset, direction)[1]}"
            else:
                occ, gap = ends, ""
            return Resolution("resolved", occ[0], prov,
                              f"{head}: end of each calendar {_PERIOD[name]} from {ends[0]}{gap} → {occ[0]}, "
                              f"then every {_PERIOD[name]}", occ)
        first, desc = (apply_offset(anchor.date, offset, direction) if offset else (anchor.date + freq, name))
        occ = [first + freq * k for k in range(n)]
        return Resolution("resolved", occ[0], prov, f"{head} + {desc}, repeating {name} → {occ[0]}", occ)

    if not offset:
        return Resolution("ambiguous", trace="Deadline offset not identified")
    due, desc = apply_offset(anchor.date, offset, rule.get("direction"))
    sign = "−" if rule.get("direction") == "before" else "+"
    return Resolution("resolved", due, prov, f"{head} {sign} {desc} → {due}")


def period_ends(start: dt.date, name: str, n: int) -> list[dt.date]:
    """The first n calendar period ends on or after `start` (weeks end on Sunday; quarters are calendar
    quarters). Month-end clamping comes from relativedelta(day=31)."""
    if name == "weekly":
        first = start + dt.timedelta(days=(6 - start.weekday()) % 7)
        return [first + dt.timedelta(weeks=k) for k in range(n)]
    if name == "monthly":
        first, step = start + relativedelta(day=31), 1
    elif name == "quarterly":
        first, step = dt.date(start.year, (start.month - 1) // 3 * 3 + 3, 1) + relativedelta(day=31), 3
    else:
        first, step = dt.date(start.year, 12, 31), 12
    return [first + relativedelta(months=step * k, day=31) for k in range(n)]


def upcoming_due(o, as_of: dt.date) -> dt.date | None:
    """For a recurring obligation, the next occurrence on or after as_of (the last one once the schedule
    has run out); otherwise the stored due date. Used for display and risk, so an old first occurrence
    doesn't read as overdue forever."""
    occ = [_as_date(d) for d in (getattr(o, "next_occurrences", None) or [])]
    if not occ:
        return o.due_date
    return next((d for d in occ if d >= as_of), occ[-1])


def _as_date(v) -> dt.date:
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v))

