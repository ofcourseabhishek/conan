"""ICS/CSV export: resolved deadlines only, VALARM 7d/1d, RFC 5545 escaping + folding, CSV injection guard."""

from tests.test_review import AS_OF, seeded  # noqa: F401  (fixture re-use)


def test_ics_has_only_resolved_deadlines_with_alarms(seeded):  # noqa: F811
    client, cid, _ = seeded
    assert "BEGIN:VEVENT" not in client.get(f"/api/contracts/{cid}/export.ics").text  # nothing dated yet
    client.put(f"/api/contracts/{cid}/events/invoice_receipt", json={"date": "2026-10-03"})
    r = client.get(f"/api/contracts/{cid}/export.ics", params=AS_OF)
    assert r.headers["content-type"].startswith("text/calendar") and "attachment" in r.headers["content-disposition"]
    body = r.text
    assert body.count("BEGIN:VEVENT") == 1 and "DTSTART;VALUE=DATE:20261102" in body
    assert body.count("BEGIN:VALARM") == 2 and "TRIGGER:-P7D" in body and "TRIGGER:-P1D" in body
    raw = r.content.decode("utf-8")
    assert "\r\n" in raw and all(len(line.encode()) <= 75 for line in raw.split("\r\n"))
    unfolded = raw.replace("\r\n ", "")
    assert "SUMMARY:[Conan] Velloran Components LLP: pay" in unfolded
    assert "Attention priority:" in unfolded and "not legal advice" in unfolded


def test_ics_escapes_text():
    from app.api.exports import _fold, _ics_escape
    assert _ics_escape("a,b;c\\d\ne") == r"a\,b\;c\\d\ne"
    folded = _fold("DESCRIPTION:" + "x" * 200)
    assert all(len(p.encode()) <= 75 for p in folded.split("\r\n")) and folded.replace("\r\n ", "") == "DESCRIPTION:" + "x" * 200


def test_csv_lists_all_and_guards_formulas(seeded):  # noqa: F811
    client, cid, _ = seeded
    q = {"contract_id": cid}
    client.patch("/api/obligations/O-001", params=q,
                 json={"action": "edit", "patch": {"action": "=HYPERLINK(\"http://evil\")"}})
    r = client.get(f"/api/contracts/{cid}/export.csv", params=AS_OF)
    text = r.content.decode("utf-8-sig")
    rows = text.strip().split("\r\n")
    assert rows[0].startswith("id,section,page") and len(rows) == 5
    assert "'=HYPERLINK" in text and ",=HYPERLINK" not in text
