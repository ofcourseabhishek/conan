from app.pipeline.ingest import extract
from app.pipeline.segment import extract_glossary, extract_parties, keyword_category, segment
from tests.pdfgen import build_pdf

CAPS = dict(max_bytes=10 * 1024 * 1024, max_pages=30, timeout_s=20)


def seg(pages=None):
    doc = extract(build_pdf(pages) if pages else build_pdf(), **CAPS)
    return doc, segment(doc)


def test_sections_at_subclause_granularity():
    _, s = seg()
    assert not s.used_fallback
    refs = [c.section_ref for c in s.clauses]
    assert refs == ["Preamble", "1.1", "1.2", "2.1", "3.1", "5.1", "6.2", "6.3", "14.6", "Sch. B"]
    assert [c.id for c in s.clauses][:3] == ["C01", "C02", "C03"]


def test_clause_text_matches_offsets_and_pages():
    doc, s = seg()
    for c in s.clauses:
        assert doc.doc_text[c.char_start:c.char_end] == c.text
        assert c.text == c.text.strip()
    by_ref = {c.section_ref: c for c in s.clauses}
    assert by_ref["6.3"].page_start == by_ref["6.3"].page_end == 2
    assert by_ref["Sch. B"].page_start == 3


def test_bare_article_heading_merges_into_first_subclause():
    _, s = seg()
    c = next(c for c in s.clauses if c.section_ref == "6.2")
    assert c.text.startswith("6. PAYMENT")
    assert c.heading == "Invoicing"


def test_wrapped_line_starting_with_number_is_not_a_heading():
    _, s = seg()
    c = next(c for c in s.clauses if c.section_ref == "2.1")
    assert "12 months after the Effective Date" in c.text


def test_numbered_item_inside_schedule_stays_in_schedule():
    _, s = seg()
    sched = s.clauses[-1]
    assert sched.section_ref == "Sch. B" and "Net 45" in sched.text


def test_parties_and_glossary():
    _, s = seg()
    assert s.parties == [
        {"name": "Tarnwick Robotics Pvt. Ltd.", "role": "Customer"},
        {"name": "Velloran Components LLP", "role": "Supplier"},
    ]
    assert '"Goods": the robotic actuator components listed in Schedule A to this Agreement' in s.glossary
    assert len(extract_glossary("x " * 10 + ' "Term" means ' + "y" * 5000)) <= 1200


def test_party_parser_ignores_non_role_terms():
    assert extract_parties('between Acme Ltd (the "Agreement") and Foo LLP (the "Buyer")') == [
        {"name": "Foo LLP", "role": "Buyer"}]


def test_fallback_windows_when_no_headings():
    para = ["This paragraph has no numbering at all and keeps going with ordinary contract prose."] * 4
    pages = [[(para, "body")] * 6 for _ in range(2)]
    doc, s = seg(pages)
    assert s.used_fallback
    assert all(c.section_ref.startswith("¶p") for c in s.clauses)
    assert s.clauses[0].char_start == 0
    assert "".join(c.text for c in s.clauses).replace("\n", "") == doc.doc_text.replace("\n", "")


def test_keyword_category():
    assert keyword_category("Customer shall pay the invoice") == "payment"
    assert keyword_category("Either party may terminate") == "termination"
    assert keyword_category("The sky is blue") == "other"
