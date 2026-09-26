"""Evidence verification and page derivation (TRD \u00a79.1). The page shown for an obligation is
page_of(match start) in doc_text, so it is correct by construction; the LLM never supplies pages.

Uniqueness rule: a quote counts as verified only if exactly one qualifying match exists in the
scope where it was found. Found once inside the obligation's own clause -> verified (the clause
disambiguates). Found only via the page window / whole document and matched more than once ->
unverified. Conan never guesses between duplicates.
"""

from __future__ import annotations

import bisect
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

MIN_QUOTE = 20
_CHAR_MAP = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u2033": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2015": "-", "\u2212": "-",
    "\u00a0": " ", "\u2007": " ", "\u202f": " ",
}


@dataclass
class Normalized:
    text: str
    raw_index: list[int]  # raw_index[i] = offset in the raw string of normalized char i

    def raw_span(self, start: int, end: int) -> tuple[int, int]:
        return self.raw_index[start], self.raw_index[end - 1] + 1


def normalize(raw: str, base: int = 0) -> Normalized:
    """NFKC, ligatures, curly->straight quotes and dashes, soft hyphens dropped, '-\\n' joined,
    whitespace collapsed, casefolded. Keeps a map back to raw offsets (+ base)."""
    out: list[str] = []
    idx: list[int] = []
    i, n = 0, len(raw)
    while i < n:
        ch = raw[i]
        if ch == "\u00ad":
            i += 1
            continue
        if ch in "-\u2010\u2011" and i + 1 < n and raw[i + 1] == "\n" and out and out[-1].isalpha():
            i += 2  # line-break hyphenation: "obli-\ngation" -> "obligation"
            continue
        ch = _CHAR_MAP.get(ch, ch)
        for c in unicodedata.normalize("NFKC", ch).casefold():
            if c.isspace():
                if not out or out[-1] == " ":
                    continue
                c = " "
            out.append(c)
            idx.append(base + i)
        i += 1
    while out and out[-1] == " ":
        out.pop()
        idx.pop()
    return Normalized("".join(out), idx)


@dataclass
class Match:
    status: str  # "verified" | "unverified"
    reason: str  # exact|fuzzy|too_short|not_found|ambiguous
    score: int
    start: int | None = None  # raw doc offsets
    end: int | None = None
    scope: str | None = None  # clause|window|document


def _find_all_exact(hay: str, needle: str) -> list[int]:
    hits, k = [], hay.find(needle)
    while k != -1:
        hits.append(k)
        k = hay.find(needle, k + 1)
    return hits


def _fuzzy_matches(hay: str, needle: str, threshold: float) -> list[tuple[float, int, int]]:
    """Best alignment, then re-search with that region masked to detect a second qualifying match."""
    found = []
    masked = hay
    for _ in range(2):
        if len(masked) < len(needle) * 0.8:
            break
        r = fuzz.partial_ratio_alignment(needle, masked, score_cutoff=threshold)
        if r is None or r.score < threshold:
            break
        found.append((r.score, r.dest_start, r.dest_end))
        masked = masked[:r.dest_start] + "\x00" * (r.dest_end - r.dest_start) + masked[r.dest_end:]
    return found


def _search(scope_raw: str, base: int, q: str, threshold: float) -> Match | None:
    norm = normalize(scope_raw, base)
    exact = _find_all_exact(norm.text, q)
    if len(exact) == 1:
        s, e = norm.raw_span(exact[0], exact[0] + len(q))
        return Match("verified", "exact", 100, s, e)
    if len(exact) > 1:
        return Match("unverified", "ambiguous", 100)
    fz = _fuzzy_matches(norm.text, q, threshold)
    if len(fz) == 1:
        score, a, b = fz[0]
        s, e = norm.raw_span(a, b)
        return Match("verified", "fuzzy", int(score), s, e)
    if len(fz) > 1:
        return Match("unverified", "ambiguous", int(fz[0][0]))
    return None


def verify_quote(quote: str, doc_text: str, clause_span: tuple[int, int] | None,
                 page_offsets: list[tuple[int, int]]) -> Match:
    q = normalize(quote).text.strip(" \"'")
    if len(q) < MIN_QUOTE:
        return Match("unverified", "too_short", 0)
    threshold = 95.0 if len(q) < 40 else 92.0

    scopes: list[tuple[str, int, int]] = []
    if clause_span:
        cs, ce = clause_span
        scopes.append(("clause", cs, ce))
        p0, p1 = page_of(page_offsets, cs), page_of(page_offsets, max(cs, ce - 1))
        ws = page_offsets[max(0, p0 - 2)][0]
        we = page_offsets[min(len(page_offsets), p1 + 1) - 1][1]
        scopes.append(("window", ws, we))
    scopes.append(("document", 0, len(doc_text)))

    last: Match | None = None
    for name, s, e in scopes:
        m = _search(doc_text[s:e], s, q, threshold)
        if m is None:
            continue
        m.scope = name
        if m.status == "verified":
            return m
        last = m  # ambiguous here; a wider scope can only be more ambiguous
        break
    return last or Match("unverified", "not_found", 0)


def page_of(page_offsets: list[tuple[int, int]], offset: int) -> int:
    starts = [s for s, _ in page_offsets]
    return max(1, bisect.bisect_right(starts, offset))


def clause_at(clause_spans: list[tuple[str, int, int]], offset: int) -> str | None:
    for cid, s, e in clause_spans:
        if s <= offset < e:
            return cid
    return None
