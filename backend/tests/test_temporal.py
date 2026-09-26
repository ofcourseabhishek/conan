"""Temporal table tests (TRD §13): business days over weekends, month-end, leap year, unspecified
day type, unresolved stays null, before/after, literal absolute dates, recurring, conditional."""

import datetime as dt
from types import SimpleNamespace as NS

from app.pipeline.temporal import EventDate, add_business_days, event_key, parse_literal_date, resolve

D = dt.date


def ob(rule, oid="O-001", quote="", verified=True, **kw):
    base = dict(id=oid, deadline_rule=rule, trigger_event=rule.get("anchor_event"), is_conditional=False,
                evidence_status="verified" if verified else "unverified", evidence_quote=quote, field_provenance={})
    return NS(**{**base, **kw})


def rel(value, unit="day", day_type="calendar", anchor="invoice_receipt", direction="after", **kw):
    return {"kind": "relative", "offset": {"value": value, "unit": unit, "day_type": day_type},
            "direction": direction, "anchor_event": anchor, **kw}


def ev(d, source="user"):
    return EventDate(d, source)


def test_business_days_skip_weekends():
    assert add_business_days(D(2026, 10, 20), 10) == D(2026, 11, 3)  # Tue -> Tue, two weekends
    assert add_business_days(D(2026, 10, 23), 1) == D(2026, 10, 26)  # Fri -> Mon
    assert add_business_days(D(2026, 10, 26), -1) == D(2026, 10, 23)
    r = resolve(ob(rel(10, day_type="business", anchor="po_issued")), {"po_issued": ev(D(2026, 10, 20))})
    assert r.due_date == D(2026, 11, 3) and "holidays not considered" in r.trace


def test_calendar_days_and_trace():
    r = resolve(ob(rel(30)), {"invoice_receipt": ev(D(2026, 10, 3))})
    assert (r.status, r.due_date, r.provenance) == ("resolved", D(2026, 11, 2), "user_event")
    assert r.trace == "invoice_receipt (2026-10-03, user-set) + 30 calendar days → 2026-11-02"


def test_month_end_clamping_and_leap_year():
    assert resolve(ob(rel(1, unit="month")), {"invoice_receipt": ev(D(2027, 1, 31))}).due_date == D(2027, 2, 28)
    assert resolve(ob(rel(1, unit="month")), {"invoice_receipt": ev(D(2028, 1, 31))}).due_date == D(2028, 2, 29)
    assert resolve(ob(rel(1, unit="year")), {"invoice_receipt": ev(D(2028, 2, 29))}).due_date == D(2029, 2, 28)


def test_unspecified_day_type_is_calendar_with_note():
    r = resolve(ob(rel(15, day_type="unspecified")), {"invoice_receipt": ev(D(2026, 10, 1))})
    assert r.due_date == D(2026, 10, 16) and "day type not stated" in r.trace


def test_before_direction():
    r = resolve(ob(rel(90, anchor="term_end", direction="before")), {"term_end": ev(D(2027, 9, 1))})
    assert r.due_date == D(2027, 6, 3) and " − 90 calendar days" in r.trace


def test_unresolved_stays_null():
    r = resolve(ob(rel(30)), {})
    assert (r.status, r.due_date, r.provenance) == ("unresolved_trigger", None, None)
    assert resolve(ob({"kind": "relative", "anchor_event": "delivery"}), {"delivery": ev(D(2026, 1, 1))}).status == "ambiguous"
    assert resolve(ob({"kind": "none"}), {}).status == "no_deadline"


def test_completion_provenance():
    r = resolve(ob(rel(5, day_type="business", anchor="delivery")), {"delivery": ev(D(2026, 10, 1), "completion")})
    assert r.provenance == "completion" and "marked done" in r.trace


def test_absolute_only_from_literal_text_in_verified_quote():
    rule = {"kind": "absolute", "absolute_date_text": "31 March 2027"}
    ok = resolve(ob(rule, quote="Supplier shall deliver the report by 31 March  2027."), {})
    assert (ok.status, ok.due_date, ok.provenance) == ("resolved", D(2027, 3, 31), "contract_text")
    assert resolve(ob(rule, quote="deliver the report by the end of March"), {}).status == "ambiguous"
    assert resolve(ob(rule, quote="by 31 March 2027", verified=False), {}).status == "ambiguous"
    partial = {"kind": "absolute", "absolute_date_text": "31 March"}
    assert resolve(ob(partial, quote="by 31 March each year"), {}).status == "ambiguous"


def test_literal_date_parsing_is_day_first_and_complete():
    assert parse_literal_date("03/04/2027") == D(2027, 4, 3)
    assert parse_literal_date("April 3, 2027") == D(2027, 4, 3)
    assert parse_literal_date("April 2027") is None and parse_literal_date("soon") is None


def test_recurring_occurrences():
    rule = rel(15, anchor="renewal", kind="recurring", recurrence="annually")
    rule["kind"] = "recurring"
    r = resolve(ob(rule), {"renewal": ev(D(2027, 4, 1))})
    assert r.next_occurrences == [D(2027, 4, 16), D(2028, 4, 16), D(2029, 4, 16)] and r.due_date == D(2027, 4, 16)
    no_off = {"kind": "recurring", "recurrence": "quarterly", "anchor_event": "term_start"}
    assert resolve(ob(no_off), {"term_start": ev(D(2026, 11, 30))}).next_occurrences == \
        [D(2027, 2, 28), D(2027, 5, 28), D(2027, 8, 28)]


def test_conditional_pending_until_its_event_occurs():
    rule = rel(10, anchor="termination", is_conditional=True)
    assert resolve(ob(rule, is_conditional=True), {}).status == "conditional_pending"
    assert resolve(ob(rule, is_conditional=True), {"termination": ev(D(2027, 1, 4))}).due_date == D(2027, 1, 14)


def test_other_events_never_merge():
    assert event_key("O-003", "other") == "other:O-003" != event_key("O-004", "other")
    r = resolve(ob(rel(7, anchor="other"), oid="O-003"), {"other:O-004": ev(D(2027, 1, 1))})
    assert r.status == "unresolved_trigger"


def test_reviewer_entered_date_is_user_event():
    rule = {"kind": "absolute", "absolute_date": "2027-01-15"}
    r = resolve(ob(rule, field_provenance={"deadline_rule": "user"}), {})
    assert (r.due_date, r.provenance) == (D(2027, 1, 15), "user_event")
    assert resolve(ob(rule), {}).status == "ambiguous"  # the same value from the LLM is not trusted
