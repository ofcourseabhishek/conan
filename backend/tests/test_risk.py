"""Risk (TRD §9.5, §13): worked example, diamond no-saturation, unrelated-obligation stability,
band boundaries, modifiers."""

import datetime as dt
import uuid
from types import SimpleNamespace as NS

from app.pipeline.risk import band, score_all

AS_OF = dt.date(2026, 10, 28)


def o(oid, **kw):
    base = dict(id=oid, status="open", review_state="proposed", modality="must", due_date=None,
                resolution_status="no_deadline", penalty_text=None, amount=None, category="other",
                deadline_rule={"kind": "none"}, evidence_status="verified", confidence=0.9)
    return NS(**{**base, **kw})


def e(up, down, rel, status="proposed", ev="verified"):
    return NS(id=uuid.uuid4(), upstream_id=up, downstream_id=down, relation=rel, status=status,
              evidence_status=ev, evidence_quote="q", page=1)


def impact(risk):
    return next((f.points for f in risk.factors if f.factor == "Potential downstream impact"), 0)


def test_worked_example_chain():
    obls = [o("O-004", status="blocked"), o("O-007"), o("O-009"), o("O-012")]
    edges = [e("O-004", "O-007", "must_precede"), e("O-007", "O-009", "condition_for"),
             e("O-009", "O-012", "must_precede")]
    r = score_all(obls, edges, [], AS_OF)
    assert [impact(r[x]) for x in ("O-007", "O-009", "O-012")] == [24, 14, 7]
    assert [s.upstream_id for s in next(f for f in r["O-012"].factors if f.path).path] == ["O-004", "O-007", "O-009"]


def test_plan_example_o012_totals_69():
    obls = [o("O-004", status="blocked"), o("O-007"), o("O-009"),
            o("O-012", due_date=AS_OF + dt.timedelta(days=5), resolution_status="resolved",
              penalty_text="interest at 1.5% per month", amount={"value": 1840000, "currency": "INR"},
              category="payment")]
    edges = [e("O-004", "O-007", "must_precede"), e("O-007", "O-009", "condition_for"),
             e("O-009", "O-012", "must_precede")]
    conflicts = [NS(status="open", obligation_ids=["O-012"])]
    r = score_all(obls, edges, conflicts, AS_OF)["O-012"]
    assert r.score == 69 and r.band == "high"


def test_diamond_takes_max_not_sum():
    obls = [o("A", status="blocked"), o("B"), o("C"), o("D")]
    edges = [e("A", "B", "depends_on"), e("A", "C", "depends_on"), e("B", "D", "depends_on"),
             e("C", "D", "depends_on")]
    assert impact(score_all(obls, edges, [], AS_OF)["D"]) == 18  # 30 × 1 × 0.6, not 36


def test_adding_unrelated_obligation_changes_nothing_else():
    obls = [o("A", status="blocked"), o("B", category="payment")]
    edges = [e("A", "B", "must_precede")]
    before = score_all(obls, edges, [], AS_OF)
    after = score_all(obls + [o("Z", status="blocked", category="penalty")], edges, [], AS_OF)
    assert {k: v.score for k, v in before.items()} == {k: after[k].score for k in before}


def test_ineligible_edges_never_propagate():
    obls = [o("A", status="blocked"), o("B"), o("C"), o("D")]
    edges = [e("A", "B", "depends_on", ev="unverified"), e("A", "C", "depends_on", status="rejected"),
             e("A", "D", "depends_on", status="proposed")]
    r = score_all(obls, edges, [], AS_OF)
    assert impact(r["B"]) == impact(r["C"]) == 0 and impact(r["D"]) == 30
    assert impact(score_all(obls, edges, [], AS_OF, reviewed_only=True)["D"]) == 0


def test_hops_capped_at_three_and_cycles_terminate():
    obls = [o(x) for x in "ABCDE"]
    obls[0].status = "blocked"
    edges = [e("A", "B", "depends_on"), e("B", "C", "depends_on"), e("C", "D", "depends_on"),
             e("D", "E", "depends_on"), e("C", "A", "depends_on")]
    r = score_all(obls, edges, [], AS_OF)
    assert impact(r["D"]) == 11 and impact(r["E"]) == 0  # 30 × 0.36 = 10.8


def test_done_rejected_score_zero_and_do_not_propagate():
    obls = [o("A", status="blocked", review_state="rejected"), o("B"), o("C", status="done", category="payment")]
    r = score_all(obls, [e("A", "B", "depends_on")], [], AS_OF)
    assert r["A"].score == 0 and impact(r["B"]) == 0 and r["C"].score == 0


def test_time_modifiers():
    soon = AS_OF + dt.timedelta(days=3)
    r = score_all([o("M", due_date=soon), o("Y", due_date=soon, modality="may"),
                   o("C", due_date=AS_OF - dt.timedelta(days=1), resolution_status="conditional_pending")],
                  [], [], AS_OF)
    assert r["M"].score == 20 and r["Y"].score == 10 and r["C"].score == 0


def test_bands():
    assert [band(x) for x in (0, 24, 25, 49, 50, 74, 75, 100)] == \
        ["low", "low", "medium", "medium", "high", "high", "critical", "critical"]
