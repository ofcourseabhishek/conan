"""Extraction eval (TRD §13). Scores an Analysis payload against a hand-labelled gold set.

A prediction matches a gold item when the evidence-span character IoU is >= 0.5, or when clause and
actor are equal and action/object token Jaccard is >= 0.5. Matching is greedy by score.
Reports precision, recall (target >= 0.80), per-field accuracy, page accuracy for verified items
(must be 100%) and invented dates (must be 0).

  cd backend
  .venv/Scripts/python -m tests.eval_score --gold fixtures/gold.json --analysis analysis.json
  .venv/Scripts/python -m tests.eval_score --gold fixtures/gold.json --api http://localhost:8000 --contract <id>

Gold file: {"items": [{"section_ref": "6.3", "actor": "...", "action": "pay", "object": "...",
  "evidence_quote": "...", "page": 4, "deadline_kind": "relative", "offset_value": 30,
  "offset_unit": "day", "day_type": "calendar", "amount_value": null}]}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline.verify import _search, normalize  # noqa: E402

TOKEN = re.compile(r"[a-z0-9]+")
STOP = {"the", "a", "an", "of", "to", "and", "or", "all", "any", "such", "its", "their", "in", "on", "for"}


def tokens(s: str | None) -> set[str]:
    return {t for t in TOKEN.findall((s or "").lower()) if t not in STOP}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def iou(a: tuple[int, int] | None, b: tuple[int, int] | None) -> float:
    if not a or not b:
        return 0.0
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union else 0.0


def locate(quote: str, clause: dict) -> tuple[int, int] | None:
    q = normalize(quote).text
    m = _search(clause["text"], clause["char_start"], q, 92.0)
    return (m.start, m.end) if m and m.status == "verified" else None


@dataclass
class Report:
    tp: int
    n_pred: int
    n_gold: int
    field_acc: dict[str, float]
    page_acc: float | None
    invented_dates: int
    unmatched_gold: list[str]

    @property
    def precision(self) -> float:
        return self.tp / self.n_pred if self.n_pred else 0.0

    @property
    def recall(self) -> float:
        return self.tp / self.n_gold if self.n_gold else 0.0

    def render(self) -> str:
        lines = [f"precision {self.precision:.2f}  recall {self.recall:.2f} (target >= 0.80)  "
                 f"[{self.tp} matched / {self.n_pred} predicted / {self.n_gold} gold]"]
        lines += [f"  {k:<14} {v:.2f}" for k, v in self.field_acc.items()]
        lines.append(f"  page (verified) {'n/a' if self.page_acc is None else f'{self.page_acc:.2f}'} (must be 1.00)")
        lines.append(f"  invented dates  {self.invented_dates} (must be 0)")
        if self.unmatched_gold:
            lines.append("  missed: " + "; ".join(self.unmatched_gold))
        return "\n".join(lines)


def invented_dates(obligations: list[dict]) -> int:
    bad = 0
    for o in obligations:
        if o.get("due_date") is None:
            continue
        prov = o.get("date_provenance")
        if prov not in ("contract_text", "user_event", "completion"):
            bad += 1
        elif prov == "contract_text":
            text = (o.get("deadline_rule") or {}).get("absolute_date_text")
            if not text or text not in o.get("evidence_quote", "") or o.get("evidence_status") != "verified":
                bad += 1
    return bad


def score(analysis: dict, gold: list[dict]) -> Report:
    clauses = {c["section_ref"]: c for c in analysis["clauses"]}
    clause_ref = {c["id"]: c["section_ref"] for c in analysis["clauses"]}
    preds = analysis["obligations"]
    gold_spans = [locate(g["evidence_quote"], clauses[g["section_ref"]]) if g["section_ref"] in clauses else None
                  for g in gold]

    pairs = []
    for gi, g in enumerate(gold):
        for pi, p in enumerate(preds):
            span_p = (p["evidence_start"], p["evidence_end"]) if p.get("evidence_start") is not None else None
            s = iou(gold_spans[gi], span_p)
            if s < 0.5:
                same = clause_ref.get(p["clause_id"]) == g["section_ref"] and \
                    p["actor"].casefold() == g["actor"].casefold()
                j = jaccard(tokens(f"{p['action']} {p.get('object')}"), tokens(f"{g['action']} {g.get('object')}"))
                s = j if same and j >= 0.5 else 0.0
            if s > 0:
                pairs.append((s, gi, pi))
    matched_g, matched_p, matches = set(), set(), []
    for s, gi, pi in sorted(pairs, reverse=True):
        if gi not in matched_g and pi not in matched_p:
            matched_g.add(gi)
            matched_p.add(pi)
            matches.append((gold[gi], preds[pi]))

    def acc(pred_ok) -> float:
        return sum(pred_ok(g, p) for g, p in matches) / len(matches) if matches else 0.0

    def rule(p):
        return p.get("deadline_rule") or {}

    def amount_ok(g, p):
        gv, pv = g.get("amount_value"), (p.get("amount") or {}).get("value")
        if gv is None or pv is None:
            return gv is None and pv is None
        return abs(gv - pv) <= 0.005 * abs(gv)

    fields = {
        "actor": acc(lambda g, p: g["actor"].casefold() == p["actor"].casefold()),
        "deadline_kind": acc(lambda g, p: g.get("deadline_kind") == rule(p).get("kind")),
        "offset": acc(lambda g, p: (g.get("offset_value"), g.get("offset_unit"), g.get("day_type")) ==
                      ((rule(p).get("offset") or {}).get("value"), (rule(p).get("offset") or {}).get("unit"),
                       (rule(p).get("offset") or {}).get("day_type"))),
        "amount": acc(amount_ok),
    }
    verified = [(g, p) for g, p in matches if p["evidence_status"] == "verified" and g.get("page")]
    page_acc = (sum(g["page"] == p["page_start"] for g, p in verified) / len(verified)) if verified else None
    missed = [f"§{g['section_ref']} {g['actor']} {g['action']}" for i, g in enumerate(gold) if i not in matched_g]
    return Report(len(matches), len(preds), len(gold), fields, page_acc, invented_dates(preds), missed)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--analysis")
    ap.add_argument("--api")
    ap.add_argument("--contract")
    a = ap.parse_args()
    gold = json.loads(Path(a.gold).read_text(encoding="utf-8"))["items"]
    if a.analysis:
        analysis = json.loads(Path(a.analysis).read_text(encoding="utf-8"))
    else:
        import httpx
        analysis = httpx.get(f"{a.api.rstrip('/')}/api/contracts/{a.contract}/analysis", timeout=30).json()
    r = score(analysis, gold)
    print(r.render())
    sys.exit(0 if r.recall >= 0.8 and r.invented_dates == 0 and r.page_acc in (None, 1.0) else 1)


if __name__ == "__main__":
    main()
