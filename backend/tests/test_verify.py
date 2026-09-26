"""Verifier cases from TRD §13: exact, whitespace drift, ligatures, curly quotes, hyphenation,
cross-page, duplicate -> unverified, fabricated -> fail, short -> fail."""

from app.pipeline.verify import normalize, page_of, verify_quote

PAGE1 = ("6.3 Payment. Customer shall pay all undisputed amounts within thirty (30) days of receipt\n"
         "of a valid invoice. Overdue amounts shall bear interest at 1.5% per month.\n")
PAGE2 = ("7.1 Confidentiality. Each party shall keep the other party’s ﬁnancial information "
         "strictly con-\nfidential during the Term.\n"
         "9.1 Notices. All notices shall be in writing and delivered by hand.\n"
         "9.2 Copies. All notices shall be in writing and delivered by hand.\n")
DOC = PAGE1 + PAGE2
PAGES = [(0, len(PAGE1)), (len(PAGE1), len(DOC))]


def span_of(text: str) -> tuple[int, int]:
    s = DOC.index(text)
    return s, s + len(text)


def v(quote, clause=None):
    return verify_quote(quote, DOC, clause, PAGES)


def test_exact_match_gives_raw_offsets_and_page():
    q = "Customer shall pay all undisputed amounts within thirty (30) days"
    m = v(q, (0, len(PAGE1)))
    assert m.status == "verified" and m.reason == "exact" and m.score == 100
    assert DOC[m.start:m.end] == q and page_of(PAGES, m.start) == 1 and m.scope == "clause"


def test_whitespace_drift_across_line_break():
    m = v("within thirty (30) days of receipt of a valid invoice", (0, len(PAGE1)))
    assert m.status == "verified" and "receipt\nof a valid" in DOC[m.start:m.end]


def test_ligature_curly_quote_and_hyphenation():
    m = v("keep the other party's financial information strictly confidential during the Term")
    assert m.status == "verified" and m.reason == "exact"
    assert page_of(PAGES, m.start) == 2 and DOC[m.end - 4:m.end] == "Term"


def test_cross_page_quote_reports_both_pages():
    q = "interest at 1.5% per month. 7.1 Confidentiality. Each party shall keep"
    m = v(q)
    assert m.status == "verified"
    assert (page_of(PAGES, m.start), page_of(PAGES, m.end - 1)) == (1, 2)


def test_small_paraphrase_passes_fuzzy():
    m = v("Customer shall pay all the undisputed amounts within thirty (30) days of receipt of a valid invoice")
    assert m.status == "verified" and m.reason == "fuzzy" and 92 <= m.score < 100


def test_duplicate_boilerplate_is_unverified():
    m = v("All notices shall be in writing and delivered by hand")
    assert m.status == "unverified" and m.reason == "ambiguous"


def test_duplicate_disambiguated_by_own_clause_verifies():
    s, _ = span_of("9.2 Copies.")
    m = v("All notices shall be in writing and delivered by hand", (s, len(DOC)))
    assert m.status == "verified" and m.start > s


def test_fabricated_quote_fails():
    m = v("Supplier shall indemnify Customer against all third-party claims whatsoever")
    assert m.status == "unverified" and m.reason == "not_found"


def test_short_quote_fails():
    assert v("shall pay").reason == "too_short"


def test_normalize_maps_back_to_raw():
    n = normalize("A­  B’s ﬁle", base=10)
    assert n.text == "a b's file"
    assert n.raw_span(0, len(n.text)) == (10, 10 + len("A­  B’s ﬁle"))
