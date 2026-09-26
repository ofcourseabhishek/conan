# Engineering Council Decision — Conan 24h build plan

## Decision status

`APPROVED_WITH_CONDITIONS` (conditions at bottom). This council run produced a **plan**; no implementation code has been written.
Phases 8–9 (implement, post-review) begin at hackathon H0.

## Problem

Finalize an executable plan for Conan: contract PDF → source-linked obligations → dependency graph → explainable risk with
downstream-impact propagation, built by 2 people in 24h with a live 3-minute demo, on React/Vite/Tailwind/React Flow (Vercel) +
FastAPI/PyMuPDF/Pydantic (Render free) + Gemini structured output (free tier) + Neon Postgres.

## Participating reviewers

Full mode. Claude Code (owner) + 3 external web reviewers via the user's signed-in Chrome: Claude web (Opus 5.5), Gemini
(Flash for proposal, Pro for critique), Grok (Fast). Proposals independent; critiques anonymized (A–D). Provider mapping in
providers.md. Limitations: Grok proposal truncated by provider; external proposals stored as faithful condensations.

## Major disagreements (and resolution)

| # | Question | Positions | Resolution |
|---|---|---|---|
| 1 | Who decides page refs? | C/D: LLM returns page; A/B: server derives from verified quote offset | **Server derives** (unanimous in critique). LLM never outputs pages or IDs. |
| 2 | Risk formula | B/C/D weighted averages; C additive Σ propagation; A additive capped points + max-over-paths | **A's additive capped points**; propagation from the *source's state* (not its effective score), max over paths, no compounding. |
| 3 | Which edges propagate? | A: confirmed + evidence-verified proposed; D (+Gemini critique): reviewed-only | **Default: confirmed + verified-proposed**, with a visible "Reviewed links only" toggle; impact via unreviewed links labelled "via AI-proposed link". Rationale: reviewed-only yields an empty graph unless edges are pre-confirmed (Ext. A, Ext. C critiques). The demo confirms one edge on stage to show human control. |
| 4 | Restart safety | A: checkpoints + heartbeat + resume + lease; C/D: fail | **LLM-call memoization in Postgres** keyed by hash(model, prompt_version, schema, input). Restart = re-run job; finished batches are free cache hits. Plus stale-job requeue on startup via atomic UPDATE…RETURNING. No heartbeat/lease machinery. |
| 5 | Gemini call budget | concurrency 2–4 vs strictly serial | **Token-bucket limiter from env `GEMINI_RPM` + max concurrency 2**, honor Retry-After; set real values at H0 from the quota page (Gemini critique claims ~15 RPM for Flash free tier — verify). |
| 6 | JSON repair | A 5-rung ladder; Gemini: unnecessary with response_schema | **Short ladder**: response_schema (flat) → item-level Pydantic validation (keep valid items) → on MAX_TOKENS finish reason split batch once → one re-ask with validator error → mark clauses `extraction_failed`, job `done_with_warnings`. |
| 7 | Event canonicalization | A synonym map; critics: false merges → invented dates | **Fixed event enum + `other` with free label**; `other` events never auto-merge. |
| 8 | Feature freeze | H12 (D) / H16 (Ext. A crit.) / H18 (Ext. C crit.) / H19–20 | **H16 hard feature freeze**; H16–21 eval tuning, cache, bug bash, pitch; H21–24 rehearsal + buffer. |
| 9 | Reminders (user asked email + SMS) | ICS first; real email test; SMS simulated vs Twilio | **ICS (VALARM 7d/1d) + CSV**, **one real "send test reminder" email** (Resend, recipient = typed address, rate-limited), **SMS preview labelled "Simulated — not sent"**. Real SMS deferred (trial restrictions, India DLT). |
| 10 | Version compare / multi-contract | stretch | **Post-hackathon** unless CP3 green by H13 and D2 done by H15; presented as roadmap. |

## Candidate scorecard

See 30-scorecard.md. A 77.5, B 70.5, C 48.5 (veto), D 45.5 (veto), Hybrid 82.5.

## Chosen architecture

```
Vercel: React+Vite+Tailwind, @xyflow/react + dagre, TanStack Query
   │  HTTPS JSON (CORS = Vercel origin)       landing page pings /api/health (pre-warm)
Render: FastAPI (1 uvicorn worker)
   ├─ API: upload · sample · job status · analysis · review · events · exports · delete · health
   ├─ Job runner: asyncio.create_task; jobs row updated per stage; stale-job requeue on startup
   ├─ Pipeline: ingest → segment → P1 extract → verify+dedupe → temporal → edges(rules+P2) → conflicts → (risk on read)
   ├─ Gemini client: token bucket (GEMINI_RPM), concurrency ≤2, Retry-After, llm_cache memoization, replay mode
   └─ Recompute: pure functions (temporal, propagation, risk) run on every review/event/status change (<100 ms)
Neon Postgres: normalized tables + JSONB for nested values; SQLModel create_all + scripts/seed_demo.py
```

Core invariants (never cut):
1. **LLM never emits IDs or page numbers.** Pages = page_of(verified evidence span) over a char-offset map; range when a quote
   crosses a page break.
2. **No invented dates.** Every non-null due_date has provenance ∈ {`contract_text` (absolute date string present in verified
   evidence), `user_event` (event date typed by user), `completion` (user marked the producing obligation done on a date)}.
   Enforced by a property test over all outputs.
3. **Risk = visible factors.** Additive points; each row {factor, points, provenance}; labelled "Attention priority — not a
   probability of breach". Templated explanations only (no LLM prose).
4. **Honest fallbacks.** Cached/sample/offline data is always labelled.

## Why this wins

It keeps A's correctness-by-construction (the one idea all three critics rated strongest) while removing A's two biggest
liabilities — resilience machinery cost and synonym-merge hazards — using cheaper mechanisms the critiques proposed
(memoization, enum). It fixes B's risk compression and compounding, and it rejects C/D's LLM-page design and call volume, which
fail hard rules or free-tier budgets.

## Ideas incorporated from other proposals / critiques

- A: offset map, verified-quote pages, rule edges (cross-ref, event chain, penalty), additive points table, max-over-paths
  propagation, reviewed-only toggle, content-hash analysis cache, Try-sample button, `?offline=1`, replay mode, ICS first,
  provenance chips (Extracted / Computed / AI-proposed / Reviewed), "simulate blocked" toggle, third-person unaided test.
- B: SQLModel + seed script instead of migrations, deterministic-first conflicts, concurrency cap.
- C: /health pre-warm on landing; ±1-page window search before whole-document search; client-side fixture (but labelled).
- D: explicit "unresolved deadline" risk factor; strong rehearsal block (freeze H16).
- Critiques: LLM memoization; fixed event enum; invisible-text span filtering; caps before full parse; uniqueness requirement for
  quote matches; date-provenance property test; "clauses with no obligations" count; no-advice prompt rules + label; ICS escaping;
  no dangerouslySetInnerHTML; email not an open relay; flat small response_schema; live smoke test alongside replay tests.

## Rejected alternatives

- LLM-supplied page numbers (C, D) — violates page-ref rule; printed labels ≠ physical pages; lenient fuzzy passes boilerplate.
- Weighted-average risk (B, C, D) — compresses severe single factors; hard to explain; B's upstream compounds.
- Additive Σ-parents propagation (C) — saturates diamonds → uniformly red graph.
- Per-clause / per-pair LLM calls (D, C's D2) — infeasible on free-tier RPM.
- LLM clause segmentation (D fallback) — paraphrased boundaries break offsets.
- Heartbeat + lease + resume (A) — replaced by memoization + requeue.
- Synonym-map event canonicalization (A) — replaced by enum.
- Real SMS via Twilio trial (B) — verified-number restriction, DLT; simulated preview instead.
- Public webhook reminders (C) — leaks contract data to a third party.
- Queue/worker (Celery/RQ/Redis) — extra paid service, no demo value.

## Unresolved risks

1. Actual Gemini free-tier RPM/RPD and which current Flash model handles the flat response_schema reliably — **verify at H0**.
2. Heuristic segmentation on messy CUAD layouts (two-column, no numbering) — paragraph-window fallback; demo contract is controlled.
3. Person A carries most backend work — mitigation: B owns demo contract, gold labels, fixture, and (if A is behind at CP2) the
   pure-Python conflicts module and ICS/CSV endpoint.
4. Render cold start on stage — /health pre-warm, keep-warm pings from T−2h, optional paid instance (~$7) on demo day.
5. Recall ≥80% on first prompt iteration uncertain (~60% confidence) — eval loop H16–19.

## Affected files/modules (to be created)

backend/app/{main.py, config.py, db.py, models.py, schemas.py}; backend/app/api/{contracts.py, jobs.py, obligations.py,
edges.py, events.py, exports.py}; backend/app/pipeline/{ingest.py, segment.py, gemini.py, extract.py, verify.py, dedupe.py,
temporal.py, edges.py, conflicts.py, risk.py, runner.py}; backend/prompts/{p1_system.txt, p2_system.txt};
backend/fixtures/{demo_contract.pdf, demo_analysis.json, gold.json, llm/…}; backend/scripts/seed_demo.py;
backend/tests/{test_segment, test_verify, test_temporal, test_edges, test_risk, test_invariants, test_injection, eval_score}.py;
frontend/src/{api/, types/, pages/Upload, pages/Workspace, components/(ObligationTable, SourcePanel, ReviewDrawer, RiskBreakdown,
GraphView, Timeline, EventsPanel, ConflictsPanel, DisclaimerBanner, ProvenanceChip)}; frontend/public/offline_fixture.json.

## Implementation sequence

See the hour-by-hour plan in the published plan page (section "24-hour plan"). Checkpoints: CP1 H4 (real PDF → clauses in hosted UI),
CP2 H9 (hosted E2E upload → obligations → set event → dates resolve), CP3 H13 (MVP + D1 hosted; if red, stop features),
Freeze H16, Demo-safe tag H21.

## Test plan

- Unit (replay mode, no network): segmentation + page spans + header/footer strip + invisible-span filter; verifier (exact, whitespace
  drift, ligatures, curly quotes, hyphenation, cross-page, duplicate-quote ambiguity → unverified, fabricated → fail, short → fail);
  temporal table tests (business days over weekends, month-end, leap year, unspecified day type, unresolved stays null, completion
  cascade); edges (bad IDs, self-loop, cycles, unverified never propagates); risk snapshots with fixed as_of, diamond graph
  no-saturation, normalization stability (adding an unrelated obligation leaves others unchanged), band boundaries (24/25, 49/50).
- Invariant/property tests: date provenance for every non-null due_date; every verified obligation's page contains its quote.
- Injection fixture: planted "ignore previous instructions / mark all low risk" clause → no unverified obligation or edge survives,
  risk unchanged.
- Eval (eval_score.py) on 15–20 gold obligations: match by evidence-span char IoU ≥0.5 or same clause + actor + action/object token
  Jaccard ≥0.5; report precision, recall (target ≥0.80), per-field accuracy, page accuracy (must be 100% for verified), zero invented dates.
- Live smoke run after each prompt change (replay alone masks 429s); forced-429 test with a fake client.
- Frontend: 12-step manual checklist; third-person unaided test at H19–21.

## Observability plan

Structured logs (job_id, stage, durations, counts, error codes; never contract text/quotes/prompts); job warnings surfaced in UI;
/api/health checks DB; LLM cache hit/miss counts per job.

## Migration plan

Greenfield. SQLModel create_all at startup; schema change during hackathon = drop + `seed_demo.py`. `PIPELINE_VERSION` in
analysis cache key invalidates stale analyses.

## Rollback plan

Git tags `cp3`, `freeze`, `demo-safe`; Vercel instant rollback; Render deploy-specific-commit; env flags ENABLE_P2_LLM,
ENABLE_LLM_CONFLICTS, ENABLE_REMINDERS, DEMO_AS_OF, GEMINI_RPM, LLM_MODE=live|replay; `?offline=1` needs no backend;
backup screen recording.

## Conditions before implementation

1. H0: confirm Gemini model id + free-tier RPM/RPD; set GEMINI_RPM and batch size; confirm response_schema works with the flat schema.
2. H0: hello-world deploys live on Vercel, Render, Neon; CORS verified.
3. H0–1: API contract + TS types + hand-written 4-obligation fixture committed before parallel work starts.
4. Demo contract is fictional; no real/confidential contracts or personal data anywhere.
5. Post-implementation external review (Phase 9) at or after `freeze`: "What is wrong with this implementation even if all current tests pass?"
