import copy
import json
from pathlib import Path

from tests.eval_score import invented_dates, score

FIXTURE = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "demo_analysis.json").read_text(encoding="utf-8"))

GOLD = [
    {"section_ref": "3.1", "actor": "Velloran Components LLP", "action": "deliver", "object": "Goods",
     "evidence_quote": "Supplier shall deliver the Goods specified in each Purchase Order to the Customer's Pune facility",
     "page": 2, "deadline_kind": "relative", "offset_value": 10, "offset_unit": "day", "day_type": "business",
     "amount_value": None},
    {"section_ref": "6.3", "actor": "Tarnwick Robotics Pvt. Ltd.", "action": "pay", "object": "undisputed amounts",
     "evidence_quote": "Customer shall pay all undisputed amounts within thirty (30) days of receipt of a valid invoice",
     "page": 4, "deadline_kind": "relative", "offset_value": 30, "offset_unit": "day", "day_type": "calendar",
     "amount_value": None},
    {"section_ref": "12.1", "actor": "Velloran Components LLP", "action": "give notice", "object": "termination",
     "evidence_quote": "either party may terminate this Agreement on sixty (60) days' written notice",
     "page": 7, "deadline_kind": "relative", "offset_value": 60, "offset_unit": "day", "day_type": "unspecified",
     "amount_value": None},
]


def test_scores_fixture_against_gold():
    r = score(FIXTURE, GOLD)
    assert r.tp == 2 and r.n_gold == 3 and r.n_pred == 4
    assert round(r.recall, 2) == 0.67 and r.precision == 0.5
    assert r.field_acc["actor"] == 1.0 and r.field_acc["offset"] == 1.0
    assert r.page_acc == 1.0 and r.invented_dates == 0
    assert r.unmatched_gold == ["§12.1 Velloran Components LLP give notice"]
    assert "recall 0.67" in r.render()


def test_wrong_page_is_reported():
    a = copy.deepcopy(FIXTURE)
    next(o for o in a["obligations"] if o["id"] == "O-012")["page_start"] = 5
    assert score(a, GOLD).page_acc == 0.5


def test_invented_dates_detected():
    good = {"due_date": "2026-11-03", "date_provenance": "user_event"}
    no_prov = {"due_date": "2026-11-03", "date_provenance": None}
    lit_missing = {"due_date": "2027-03-31", "date_provenance": "contract_text", "evidence_status": "verified",
                   "evidence_quote": "pay by the end of the financial year", "deadline_rule": {"absolute_date_text": "31 March 2027"}}
    lit_ok = {**lit_missing, "evidence_quote": "shall pay on or before 31 March 2027"}
    assert invented_dates([good, no_prov, lit_missing, lit_ok]) == 2
