# Scorecard (rubric: reference/scoring-rubric.md; 0–10 per dimension; weighted to 100)

Scored on arguments and critiques, not model identity. "Hybrid" = the design adopted in 40-decision.md.

| Dimension (weight) | A (Ext. A) | B (Claude Code) | C (Ext. B) | D (Ext. C) | Hybrid |
|---|---:|---:|---:|---:|---:|
| Correctness (20) | 9 | 7 | 4 | 4 | 9 |
| Simplicity (10) | 5 | 7 | 6 | 8 | 7 |
| Reliability (15) | 9 | 8 | 4 | 3 | 9 |
| Security & privacy (10) | 7 | 6 | 4 | 5 | 8 |
| Maintainability (10) | 7 | 8 | 6 | 6 | 8 |
| Testability (10) | 9 | 7 | 5 | 4 | 9 |
| Performance (10) | 7 | 6 | 5 | 3 | 8 |
| Scalability (5) | 6 | 6 | 5 | 3 | 6 |
| Compatibility (5) | 8 | 8 | 7 | 7 | 8 |
| Migration/rollback (5) | 8 | 7 | 5 | 4 | 8 |
| **Weighted total** | **77.5** | **70.5** | **48.5** | **45.5** | **82.5** |
| Veto | — | — | **Yes**: LLM-supplied pages shown even when unverified (violates hard page-ref rule); additive Σ propagation saturates | **Yes**: no precomputed demo fallback (hard rule); per-clause call volume infeasible on free tier; no restart handling | — |

## Evidence behind key scores
- A correctness 9: pages derived from verified quote offsets (all 3 critics: strongest idea). Minus: duplicate-quote reassignment and
  synonym-merge hazards (Ext. A, Ext. C critiques).
- A simplicity 5: 5-rung ladder + heartbeat/lease/resume + synonym table ≈ 30% of budget on resilience (Ext. A critique).
- B correctness 7: weighted average compresses severe single factors; upstream compounds via effective risk (Ext. A, Ext. B critiques).
- B performance 6: concurrency 4 likely to 429 on free tier (Ext. B critique; limit to be verified at H0).
- C/D correctness 4: LLM pages + lenient fuzzy (≥85 / ≥0.8) pass boilerplate on wrong pages (all critics).
- Hybrid simplicity 7: LLM-call memoization replaces heartbeat/lease/resume; fixed event enum replaces synonym table; shortened ladder.

## Rankings from each reviewer
| Reviewer | Ranking |
|---|---|
| External A (Claude web, Opus 5.5) | A > B > C > D |
| External B (Gemini, Pro) | A > B > D > C |
| External C (Grok, Fast) | A > B > C > D |
| Claude Code (self, after rebuttal) | A > B > C > D; concedes B's risk formula |
