"""Stage 7: potential conflicts, D2 (TRD §9.4). Deterministic first; Conan flags, never decides.

Rule conflicts compare obligations about the same duty (same actor, category, trigger event and
action stem) in DIFFERENT clauses: different offsets (weeks -> days), different day types (neither
unspecified), amounts differing by more than 1%, or different absolute dates. Notice periods
("60 days' written notice") are compared between clauses of the same category.
LLM conflicts (P2 `potential_conflicts`, behind ENABLE_LLM_CONFLICTS) are kept only if both quotes verify.
"""

from __future__ import annotations

import re
import uuid
from itertools import combinations

from app.models import Conflict
from app.pipeline.verify import _search, normalize, page_of

COPY_TAIL = ("These may be inconsistent. Conan does not determine which prevails; "
             "check the order-of-precedence clause or ask counsel.")
_STEMS = {"pay": "pay", "paid": "pay", "payment": "pay", "pays": "pay", "remit": "pay",
          "deliver": "deliver", "delivers": "deliver", "delivery": "deliver", "ship": "deliver",
          "invoice": "invoice", "invoices": "invoice", "bill": "invoice",
          "notify": "notify", "notice": "notify", "give": "notify",
          "terminate": "terminate", "termination": "terminate", "renew": "renew", "renewal": "renew",
          "inspect": "inspect", "inspection": "inspect", "submit": "submit", "provide": "submit"}
_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "fourteen": 14, "fifteen": 15, "twenty": 20, "twenty-one": 21, "twenty one": 21,
            "thirty": 30, "forty-five": 45, "forty five": 45, "sixty": 60, "ninety": 90,
            "one hundred twenty": 120, "one hundred and twenty": 120, "hundred twenty": 120,
            "one hundred eighty": 180, "one hundred and eighty": 180}
# Longest number words first, bounded, so a preceding word ("upon sixty") is never swallowed into the number.
_NUMWORDS = "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in sorted(_WORDNUM, key=len, reverse=True))
_NOTICE = re.compile(
    r"\b(?P<num>\d+|" + _NUMWORDS + r")\s*(?:\(\s*(?P<paren>\d+)\s*\))?\s*(?P<biz>business\s+)?days?['’]?\s+"
    r"(?:prior\s+|advance\s+)?(?:written\s+)?notice", re.I)


def action_stem(action: str | None) -> str:
    words = re.findall(r"[a-z]+", (action or "").lower())
    for w in words:
        if w in _STEMS:
            return _STEMS[w]
    return words[0] if words else ""


def _days(offset: dict | None) -> int | None:
    if not offset or offset.get("value") is None:
        return None
    unit = offset.get("unit")
    if unit == "day":
        return offset["value"]
    if unit == "week":
        return offset["value"] * 7
    return None  # months/years are compared only against the same unit


def _describe(o, sections) -> str:
    r = o.deadline_rule or {}
    off = r.get("offset") or {}
    what = f"{o.action} {o.object or ''}".strip()
    if r.get("kind") == "absolute" and r.get("absolute_date_text"):
        when = f"by {r['absolute_date_text']}"
    elif off:
        dt_word = {"business": " business", "calendar": " calendar"}.get(off.get("day_type"), "")
        unit = off.get("unit", "day") + ("s" if off.get("value") != 1 else "")
        anchor = (r.get("anchor_event") or o.trigger_event or "the trigger").replace("_", " ")
        when = f"within {off.get('value')}{dt_word} {unit} of {anchor}"
    else:
        when = ""
    amt = f" ({o.amount.get('currency') or ''} {o.amount.get('value'):,.0f})".replace("( ", "(") if o.amount else ""
    return f"{sections.get(o.clause_id, '?')} (p. {o.page_start}) sets: {what} {when}{amt}".strip()


def _pair_kind(a, b) -> str | None:
    ra, rb = a.deadline_rule or {}, b.deadline_rule or {}
    oa, ob = ra.get("offset") or {}, rb.get("offset") or {}
    da, db = _days(oa), _days(ob)
    if da is not None and db is not None and da != db:
        return "offset_mismatch"
    if oa and ob and oa.get("unit") == ob.get("unit") and oa.get("unit") in ("month", "year") \
            and oa.get("value") != ob.get("value"):
        return "offset_mismatch"
    ta, tb = oa.get("day_type"), ob.get("day_type")
    if ta and tb and "unspecified" not in (ta, tb) and ta != tb:
        return "day_type_mismatch"
    if a.amount and b.amount:
        va, vb = a.amount.get("value"), b.amount.get("value")
        if va and vb and abs(va - vb) > 0.01 * max(abs(va), abs(vb)):
            return "amount_mismatch"
    if ra.get("absolute_date") and rb.get("absolute_date") and ra["absolute_date"] != rb["absolute_date"]:
        return "date_mismatch"
    return None


def rule_conflicts(contract_id: uuid.UUID, obligations, clauses) -> list[Conflict]:
    sections = {c.id: f"§{c.section_ref}" if c.section_ref and c.section_ref[0].isdigit() else (c.section_ref or c.id)
                for c in clauses}
    active = [o for o in obligations if o.review_state != "rejected" and o.status != "waived"]
    groups: dict[tuple, list] = {}
    for o in active:
        key = (o.actor.casefold(), o.category, o.trigger_event or "", action_stem(o.action))
        groups.setdefault(key, []).append(o)
    out: list[Conflict] = []
    for members in groups.values():
        for a, b in combinations(sorted(members, key=lambda o: o.id), 2):
            if a.clause_id == b.clause_id:
                continue
            kind = _pair_kind(a, b)
            if kind:
                out.append(Conflict(
                    contract_id=contract_id, kind=kind, source="rule", obligation_ids=[a.id, b.id],
                    clause_a=a.clause_id, clause_b=b.clause_id,
                    description=f"{_describe(a, sections)}; {_describe(b, sections)}. {COPY_TAIL}",
                    quote_a=a.evidence_quote, quote_b=b.evidence_quote))
    out += _notice_conflicts(contract_id, active, clauses, sections)
    return out


def _notice_days(m: re.Match) -> int | None:
    if m.group("paren"):
        return int(m.group("paren"))
    n = " ".join(m.group("num").lower().split())
    return int(n) if n.isdigit() else _WORDNUM.get(n)


def _notice_conflicts(contract_id, active, clauses, sections) -> list[Conflict]:
    by_clause = {}
    for o in active:
        by_clause.setdefault(o.clause_id, []).append(o)
    found: dict[str, list[tuple]] = {}  # category -> [(clause, days, quote)]
    for c in clauses:
        obls = by_clause.get(c.id, [])
        cats = {o.category for o in obls} & {"termination", "renewal"}
        if not cats:
            continue
        for m in _NOTICE.finditer(c.text):
            d = _notice_days(m)
            if d:
                s = max(c.text.rfind(".", 0, m.start()) + 1, m.start() - 120)
                quote = " ".join(c.text[s:m.end()].split())
                for cat in cats:
                    found.setdefault(cat, []).append((c, d, quote))
                break  # first notice period per clause
    out = []
    for cat, items in found.items():
        for (ca, da, qa), (cb, db, qb) in combinations(items, 2):
            if da != db and ca.id != cb.id:
                ids = sorted({o.id for o in by_clause[ca.id] + by_clause[cb.id] if o.category == cat})
                out.append(Conflict(
                    contract_id=contract_id, kind="notice_period", source="rule", obligation_ids=ids,
                    clause_a=ca.id, clause_b=cb.id,
                    description=(f"{sections[ca.id]} (p. {ca.page_start}) sets {da} days' notice for {cat}; "
                                 f"{sections[cb.id]} (p. {cb.page_start}) sets {db} days' notice. {COPY_TAIL}"),
                    quote_a=qa, quote_b=qb))
    return out


def llm_conflicts(contract_id: uuid.UUID, proposals, obligations, doc_text: str, page_offsets) -> list[Conflict]:
    """P2 potential_conflicts, kept only if both obligations exist and both quotes verify."""
    by_id = {o.id: o for o in obligations if o.review_state != "rejected"}
    out = []
    for p in proposals:
        a, b = by_id.get(p.obligation_a), by_id.get(p.obligation_b)
        if not a or not b or a.id == b.id:
            continue
        spans = []
        for q in (p.quote_a, p.quote_b):
            qn = normalize(q).text
            m = _search(doc_text, 0, qn, 95.0 if len(qn) < 40 else 92.0) if len(qn) >= 20 else None
            spans.append(m if m and m.status == "verified" else None)
        if None in spans:
            continue
        pa, pb = page_of(page_offsets, spans[0].start), page_of(page_offsets, spans[1].start)
        out.append(Conflict(
            contract_id=contract_id, kind="llm", source="llm", obligation_ids=sorted([a.id, b.id]),
            clause_a=a.clause_id, clause_b=b.clause_id,
            description=f"AI flag (p. {pa} vs p. {pb}): {p.description[:300]} {COPY_TAIL}",
            quote_a=p.quote_a, quote_b=p.quote_b))
    return out


def merge_rule_conflicts(existing: list[Conflict], fresh: list[Conflict]) -> tuple[list[Conflict], list[Conflict]]:
    """Recompute after an edit: keep a reviewer's 'dismissed' on conflicts that still hold.
    Returns (to_add, to_delete); LLM conflicts are never touched."""
    key = lambda c: (c.kind, tuple(sorted(c.obligation_ids)))  # noqa: E731
    have = {key(c): c for c in existing if c.source == "rule"}
    want = {key(c): c for c in fresh}
    to_add = [c for k, c in want.items() if k not in have]
    to_delete = [c for k, c in have.items() if k not in want]
    for k, c in want.items():  # refresh wording/quotes on survivors
        if k in have:
            have[k].description, have[k].quote_a, have[k].quote_b = c.description, c.quote_a, c.quote_b
    return to_add, to_delete
