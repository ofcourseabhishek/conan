"""Stage 2: doc_text + lines -> clauses (TRD §5.2). Deterministic; never uses the LLM, because
paraphrased boundaries would break character offsets.

Also pulls parties and a defined-terms glossary from the text for the P1 prompt.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from app.pipeline.ingest import IngestResult, Line

MIN_CLAUSE, TARGET_MIN, MAX_CLAUSE = 60, 150, 4000
WINDOW = 1500

_NUMBERED = re.compile(
    r"^\s*(?P<kw>ARTICLE|Article|SECTION|Section|CLAUSE|Clause)?\s*"
    r"(?P<num>\d{1,2}(?:\.\d{1,2}){0,3})(?P<trail>[.)])?\s+(?P<rest>\S.*)$"
)
_ROMAN = re.compile(r"^\s*(?:ARTICLE|Article)\s+(?P<num>[IVXLC]+)\b[.:\-–— ]*(?P<rest>.*)$")
_ANNEX = re.compile(
    r"^\s*(?P<kw>SCHEDULE|Schedule|EXHIBIT|Exhibit|ANNEX|Annex|ANNEXURE|Annexure|APPENDIX|Appendix)"
    r"\s+(?P<num>[A-Z0-9]{1,3})\b[.:\-–— ]*(?P<rest>.*)$"
)
_SUBMARK = re.compile(r"^\s*\((?P<m>[a-z]|[ivx]{1,4})\)\s+\S")


@dataclass
class Heading:
    line: Line
    ref: str  # "6.3", "Art. IV", "Sch. B"
    depth: int
    heading: str | None
    top: int | None  # top-level section number, for monotonicity


@dataclass
class ClauseSpan:
    id: str
    section_ref: str
    heading: str | None
    char_start: int
    char_end: int
    page_start: int
    page_end: int
    text: str


@dataclass
class Segmentation:
    clauses: list[ClauseSpan]
    parties: list[dict]
    glossary: str
    used_fallback: bool


def _heading_title(rest: str, line: Line) -> str | None:
    rest = rest.strip()
    m = re.match(r"^([^.]{2,60})\.\s", rest + " ")
    if m and (m.group(1).istitle() or m.group(1).isupper() or len(m.group(1).split()) <= 5):
        return m.group(1).strip(" -–—:")
    if len(rest) <= 80 and (line.is_bold or rest.isupper() or rest.istitle()):
        return rest.strip(" -–—:.")
    return None


def _roman_to_int(s: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = 0
    for a, b in zip(s, s[1:] + " "):
        v = vals[a]
        total += -v if b != " " and vals.get(b, 0) > v else v
    return total


def find_headings(lines: list[Line]) -> list[Heading]:
    out: list[Heading] = []
    last_top = 0
    in_annex = False
    body_size = statistics.median([l.font_size for l in lines]) if lines else 0
    for ln in lines:
        if m := _ANNEX.match(ln.text):
            kw = m["kw"][:3].title()
            ref = f"{kw}. {m['num']}"
            out.append(Heading(ln, ref, 1, (m["rest"].strip(" -–—:.") or None), None))
            in_annex = True
            continue
        if m := _ROMAN.match(ln.text):
            n = _roman_to_int(m["num"])
            if n >= last_top:
                last_top = n
                out.append(Heading(ln, f"Art. {m['num']}", 1, _heading_title(m["rest"], ln) if m["rest"] else None, n))
            continue
        m = _NUMBERED.match(ln.text)
        if not m:
            continue
        num = m["num"]
        dotted = "." in num or m["trail"] is not None
        strong = m["kw"] is not None or ln.is_bold or ln.font_size > body_size + 0.5
        if not (dotted or strong):  # skips wrapped body lines like "30 days of receipt"
            continue
        top = int(num.split(".")[0])
        if top == 0 or (top < last_top and not in_annex) or top > 99:
            continue
        if in_annex and top < last_top:
            # numbered lines inside a schedule belong to the schedule
            continue
        last_top = top
        depth = num.count(".") + 1
        out.append(Heading(ln, num, depth, _heading_title(m["rest"], ln), top))
    return out


def _split_long(span: tuple[int, int, str], doc: IngestResult) -> list[tuple[int, int, str]]:
    s, e, ref = span
    if e - s <= MAX_CLAUSE:
        return [span]
    cuts = [ln for ln in doc.lines if s < ln.char_start < e and _SUBMARK.match(ln.text)]
    if not cuts:
        return [span]
    pieces, prev, prev_ref = [], s, ref
    for ln in cuts:
        pieces.append((prev, ln.char_start, prev_ref))
        prev, prev_ref = ln.char_start, f"{ref}({_SUBMARK.match(ln.text)['m']})"
    pieces.append((prev, e, prev_ref))
    return pieces


def _trim(doc_text: str, s: int, e: int) -> tuple[int, int]:
    while e > s and doc_text[e - 1].isspace():
        e -= 1
    while s < e and doc_text[s].isspace():
        s += 1
    return s, e


def segment(doc: IngestResult) -> Segmentation:
    text = doc.doc_text
    heads = find_headings(doc.lines)
    used_fallback = len(heads) < 3
    raw: list[tuple[int, int, str, str | None]] = []  # start, end, ref, heading

    if not used_fallback:
        # Deepest numbering level whose clauses are substantial. Levels 1-2 ("6", "6.3") are always
        # acceptable: users cite at that granularity, and over-long clauses split at (a)/(b) below.
        # Bare heading lines ("6. PAYMENT") are ignored in the median; they merge forward anyway.
        max_depth = max(h.depth for h in heads)
        chosen = [h for h in heads if h.depth == 1]
        for level in range(max_depth, 0, -1):
            cand = [h for h in heads if h.depth <= level]
            bounds = [h.line.char_start for h in cand] + [len(text)]
            lengths = [b - a for a, b in zip(bounds, bounds[1:]) if b - a >= MIN_CLAUSE] or [0]
            if level <= 2 or statistics.median(lengths) >= TARGET_MIN:
                chosen = cand
                break
        if chosen[0].line.char_start > 0:
            raw.append((0, chosen[0].line.char_start, "Preamble", None))
        for h, nxt in zip(chosen, chosen[1:] + [None]):
            end = nxt.line.char_start if nxt else len(text)
            raw.append((h.line.char_start, end, h.ref, h.heading))
    else:
        raw = _fallback_windows(doc)

    # merge tiny clauses forward (e.g. a bare "3. DELIVERY" line before 3.1), keeping the later ref
    merged: list[list] = []
    carry: int | None = None
    for s, e, ref, head in raw:
        ts, te = _trim(text, s, e)
        if te - ts < MIN_CLAUSE and ref != "Preamble":
            carry = s if carry is None else carry
            continue
        if carry is not None:
            s, carry = carry, None
        merged.append([s, e, ref, head])
    if carry is not None and merged:
        merged[-1][1] = len(text)

    clauses: list[ClauseSpan] = []
    for s, e, ref, head in merged:
        for ps, pe, pref in _split_long((s, e, ref), doc):
            ps, pe = _trim(text, ps, pe)
            if pe - ps == 0:
                continue
            clauses.append(ClauseSpan(
                id=f"C{len(clauses) + 1:02d}", section_ref=pref, heading=head,
                char_start=ps, char_end=pe, page_start=doc.page_of(ps), page_end=doc.page_of(pe - 1),
                text=text[ps:pe],
            ))
    return Segmentation(clauses, extract_parties(text[:1500]), extract_glossary(text), used_fallback)


def _fallback_windows(doc: IngestResult) -> list[tuple[int, int, str, str | None]]:
    """Pack paragraph blocks into ~WINDOW-char windows; ref = ¶p<page>-<n>."""
    starts = [ln.char_start for ln in doc.lines if ln.block_start] or [0]
    if starts[0] != 0:
        starts.insert(0, 0)
    bounds = starts + [len(doc.doc_text)]
    out, win_start, per_page = [], bounds[0], {}
    for b in bounds[1:]:
        if b - win_start >= WINDOW or b == bounds[-1]:
            p = doc.page_of(win_start)
            per_page[p] = per_page.get(p, 0) + 1
            out.append((win_start, b, f"¶p{p}-{per_page[p]}", None))
            win_start = b
    return out


# ---------------------------------------------------------------- parties + glossary

_QUOTED = r"[\"“”']([A-Z][A-Za-z0-9 &\-]{1,40})[\"“”']"
_DEFINED = re.compile(r"\((?:hereinafter\s+(?:referred\s+to\s+as\s+|called\s+)?)?(?:the\s+)?" + _QUOTED + r"\)")
_MEANS = re.compile(_QUOTED + r"\s+(?:shall\s+)?means?\s+([^.;]{3,200})")
_ROLE_WORDS = {
    "customer", "supplier", "buyer", "seller", "vendor", "purchaser", "client", "contractor", "company",
    "licensor", "licensee", "lessor", "lessee", "provider", "service provider", "distributor", "manufacturer",
    "consultant", "employer", "employee", "landlord", "tenant", "party a", "party b",
}


def extract_parties(preamble: str) -> list[dict]:
    parties: list[dict] = []
    flat = " ".join(preamble.split())
    for m in _DEFINED.finditer(flat):
        role = m.group(1).strip()
        before = flat[max(0, m.start() - 250):m.start()]
        piece = re.split(r"\b(?:between|and|by|with)\b", before, flags=re.I)[-1]
        name = piece.split(",")[0].strip(" ,:;\"“”")
        if role.lower() not in _ROLE_WORDS and not role.lower().startswith("party"):
            continue
        if not name or len(name) > 100 or not name[0].isupper():
            continue
        if all(p["name"] != name for p in parties):
            parties.append({"name": name, "role": role})
    return parties


def extract_glossary(text: str, cap: int = 1200) -> str:
    flat = " ".join(text.split())
    entries: dict[str, str] = {}
    for m in _MEANS.finditer(flat):
        entries.setdefault(m.group(1).strip(), " ".join(m.group(2).split()))
    for m in _DEFINED.finditer(flat):
        entries.setdefault(m.group(1).strip(), "")
    out, used = [], 0
    for term, definition in entries.items():
        item = f'"{term}": {definition}' if definition else f'"{term}"'
        if used + len(item) + 1 > cap:
            break
        out.append(item)
        used += len(item) + 1
    return "\n".join(out)


# ---------------------------------------------------------------- keyword category fallback

_CATEGORY_WORDS = [
    ("payment", r"\b(pay|payment|invoice|fee|price|interest|remit)"),
    ("termination", r"\b(terminat|expir)"),
    ("renewal", r"\b(renew|extension of the term)"),
    ("penalty", r"\b(liquidated damages|penalt|service credit)"),
    ("delivery", r"\b(deliver|shipment|dispatch|inspect|accept)"),
    ("confidentiality", r"\b(confidential|non-disclosure)"),
    ("compliance", r"\b(comply|compliance|insurance|certificate|audit|law|regulat)"),
]


def keyword_category(text: str) -> str:
    low = text.lower()
    best, best_n = "other", 0
    for cat, pat in _CATEGORY_WORDS:
        n = len(re.findall(pat, low))
        if n > best_n:
            best, best_n = cat, n
    return best
