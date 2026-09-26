# Anonymous cross-critique — Reviewer: External C (adversarial / red-team role), model "Fast"
Mapping (unknown to reviewer): A = External A, B = Claude Code, C = External B, D = External C (this reviewer's own proposal).
Captured near-verbatim; complete (not truncated this time).

## Part 1
**A.** Strongest: char-offset map + exact/rapidfuzz evidence (≥92/95), never trusts LLM for page/ID; deterministic rule edges
+ event cascade; additive capped risk with path-max propagation over verified edges; asyncio checkpoints + content-hash cache.
Unsupported: header/footer/heading regex + font reliably segment every legal PDF; 0.4 cap + review queue enough for judges.
Coupling: trigger/produces keys must be perfectly canonicalized or cascade fails; evidence re-search can reassign clauses silently.
Unnecessary: full repair ladder, cycle-break by lowest-conf LLM edge, plain SQL migrations, ICS+Resend+simulated SMS.
Correctness: quote-derived page can mismatch if quote occurs multiple times; event keys may create implicit dates.
State: checkpoints + resume solid; cold start/free tier still lose in-flight. Security: prompt injection via PDF text; no
sanitization mentioned. Missing tests: adversarial PDF, multi-occurrence quotes, cycle graphs, resume mid-batch.
Simpler: drop rule edges + synonym table; pure P2 edges + human review gate.

**B.** Strongest: same solid pipeline; weighted average simpler to explain. Unsupported: linear factors; create_all, no migrations.
Coupling: same event keys + upstream max; purely deterministic conflicts may miss LLM-detected ones. Unnecessary: Twilio/late SMS;
concurrency 4 with 1 retry. Correctness: risk less transparent (weights hide contributions). Missing: weight sensitivity tests.
Simpler: keep A's additive table; drop Twilio.

**C.** Strongest: LLM page + verify/correct ±1; small batches; client fixture + health ping.
Unsupported: LLM page trustworthy; additive parent sum won't explode; JSONB blob queryable. Coupling: page correction mutates
obligation silently; proposed ×0.7 still propagates bad data. Unnecessary: per-pair micro-prompt D2; public webhook.
Correctness: high wrong-page risk on weak/multi-page quotes; invented dates possible if temporal JSONB not strictly relative; risk
not fully reproducible. State: no resume, 90s stale harsh under cold starts. Security: webhook + LLM page widen surface.
Simpler: drop LLM page (use A's map); no Tarjan at depth 3.

**D.** Strongest: human-reviewed-only propagation (safest); early freeze + long rehearsal. Unsupported: per-clause calls scale;
LLM segmentation reliable; 0.8 fuzzy enough. Coupling: propagation gated on review that may never happen in demo. Correctness: LLM
page + low fuzzy → wrong refs; silent wrong info if review skipped. State: no resume → total loss on restart. "Too simple".

## Part 2 — red team
Most likely false (all): segmentation + fuzzy alignment yields correct page refs on real multi-column contract PDFs under free-tier
latency. Partial failure: 429 mid-job → A/B resume from checkpoint (best), C/D fail/lose everything; Neon blip → A/B may retry, C
worse; Render restart → only A/B recover in-flight work. Adversarial PDFs: header-heavy, repeated boilerplate, image-only pages,
**injected "Section X.Y due tomorrow"** → wrong pages, relative dates treated as absolute, evidence matched on wrong occurrence;
injection can force high-risk or false edges. Tests that pass while wrong: happy-path demo PDF + unit fuzzy + cycle-free graph →
still wrong pages on multi-occurrence quotes, silent invented dates, risk that looks reproducible but omits unverified edges.
Silent wrong info: LLM page without proof (C/D); auto-propagating unverified edges; bands hiding the factor table; "cached" demo that
looks live; unresolved deadlines rendered as concrete dates.

## Part 3
Fatal: **C** (LLM page + no resume + additive explosion); **D** (no resume + LLM page + review-gated propagation demos will skip).
A/B none. **Rank A > B > C > D** (reviewer ranked its own proposal last, unknowingly).
Hybrid: A's offset map + evidence alignment + rule/event-chain edges + P2; A's additive capped risk + path-max (verified only) +
reviewed-only toggle; A's checkpoints + resume + content-hash cache + offline fixture; B's weighted average as optional display
mode; C's small batches + health ping + client fixture; D's early-freeze discipline moved to **H18**. Drop LLM page numbers, Tarjan,
Twilio, public webhook, JSONB blob.
Top 5: never LLM page/ID; evidence exact+fuzzy+reassign with confidence penalty; risk only over verified edges + visible factors;
checkpoint/resume under free tier; relative deadlines stay unresolved + demo cache.
Would change mind: adversarial PDFs showing C's page-verify >95% while A's map fails; measured resume success under forced
429+restart; user study showing weighted risk more explainable than additive.
