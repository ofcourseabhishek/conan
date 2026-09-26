"""Property tests for the never-cut invariants (TRD §13).

1. Every non-null due_date has provenance in {contract_text, user_event, completion}; for
   contract_text the date string appears in the verified quote.
2. Every verified obligation's page range contains its quote.
Hand-rolled generator (seeded) to avoid a hypothesis dependency.
"""

import datetime as dt
import random
from types import SimpleNamespace as NS

from app.pipeline.temporal import EventDate, event_key, resolve
from tests.eval_score import invented_dates

EVENTS = ["po_issued", "delivery", "acceptance", "invoice_receipt", "term_end", "renewal", "other", None]
KINDS = ["absolute", "relative", "recurring", "none"]
DATE_TEXTS = ["31 March 2027", "1 April 2027", "April 2027", "03/04/2027", "next Tuesday", None]


def random_obligation(rng: random.Random, i: int):
    anchor = rng.choice(EVENTS)
    kind = rng.choice(KINDS)
    text = rng.choice(DATE_TEXTS)
    quote_has = rng.random() < 0.5 and text
    rule = {
        "kind": kind, "anchor_event": anchor, "absolute_date_text": text,
        "absolute_date": rng.choice([None, "2027-05-05"]),
        "offset": rng.choice([None, {"value": rng.randint(0, 120), "unit": rng.choice(["day", "week", "month", "year"]),
                                     "day_type": rng.choice(["calendar", "business", "unspecified"])}]),
        "direction": rng.choice(["after", "before", None]),
        "recurrence": rng.choice([None, "weekly", "monthly", "quarterly", "annually"]),
        "is_conditional": rng.random() < 0.2,
    }
    return NS(id=f"O-{i:03d}", deadline_rule=rule, trigger_event=anchor, is_conditional=rule["is_conditional"],
              evidence_status=rng.choice(["verified", "unverified"]),
              evidence_quote=f"shall do it by {text}" if quote_has else "shall do it promptly",
              field_provenance=rng.choice([{}, {"deadline_rule": "user"}, {"deadline_rule": "extracted"}]))


def test_no_invented_dates_property():
    rng = random.Random(20260926)
    resolved = 0
    for trial in range(300):
        obls = [random_obligation(rng, i) for i in range(1, 9)]
        events = {}
        for key in EVENTS[:-1]:
            if rng.random() < 0.5:
                events[key] = EventDate(dt.date(2026, 1, 1) + dt.timedelta(days=rng.randint(0, 900)),
                                        rng.choice(["user", "completion"]))
        for o in obls:
            if o.trigger_event == "other" and rng.random() < 0.5:
                events[event_key(o.id, "other")] = EventDate(dt.date(2026, 6, 1), "user")
        rows = []
        for o in obls:
            r = resolve(o, events)
            if r.due_date is None:
                assert r.provenance is None and r.status != "resolved"
                continue
            resolved += 1
            assert r.provenance in ("contract_text", "user_event", "completion"), (o, r)
            if r.provenance == "contract_text":
                assert o.evidence_status == "verified"
                assert " ".join(o.deadline_rule["absolute_date_text"].split()).casefold() in o.evidence_quote.casefold()
            if r.provenance in ("user_event", "completion") and o.field_provenance.get("deadline_rule") != "user":
                anchor = events[event_key(o.id, o.deadline_rule["anchor_event"])]
                assert r.provenance == {"user": "user_event", "completion": "completion"}[anchor.source]
            rows.append({"due_date": r.due_date.isoformat(), "date_provenance": r.provenance,
                         "evidence_status": o.evidence_status, "evidence_quote": o.evidence_quote,
                         "deadline_rule": o.deadline_rule})
        assert invented_dates(rows) == 0
    assert resolved > 200  # the generator actually exercises resolution


def test_verified_pages_contain_their_quotes():
    import uuid

    from app.pipeline.dedupe import ClauseRef, build_rows, dedupe, verify_all
    from app.pipeline.ingest import extract
    from app.pipeline.llm_schemas import P1Obligation
    from app.pipeline.segment import segment
    from tests.pdfgen import build_pdf
    from tests.test_extract import ob

    d = extract(build_pdf(), max_bytes=10**7, max_pages=30, timeout_s=20)
    seg = segment(d)
    refs = [ClauseRef(c.id, c.char_start, c.char_end, c.page_start) for c in seg.clauses]
    rng = random.Random(7)
    items = []
    for _ in range(200):  # random verbatim windows of the document, attributed to random clauses
        c = rng.choice(seg.clauses)
        a = rng.randint(0, max(0, len(c.text) - 40))
        items.append(P1Obligation(**ob(rng.choice(seg.clauses).id, c.text[a:a + rng.randint(25, 120)],
                                       action=f"act{rng.randint(0, 10**6)}")))
    rows = build_rows(uuid.uuid4(), dedupe(verify_all(items, refs, d.doc_text, d.page_offsets, seg.parties)),
                      {c.id: c.char_start for c in seg.clauses})
    checked = 0
    for r in rows:
        if r.evidence_status != "verified":
            continue
        checked += 1
        s, e = d.page_offsets[r.page_start - 1][0], d.page_offsets[r.page_end - 1][1]
        assert s <= r.evidence_start < r.evidence_end <= e
        clause = next(c for c in seg.clauses if c.id == r.clause_id)
        assert clause.char_start <= r.evidence_start < clause.char_end
    assert checked > 20
