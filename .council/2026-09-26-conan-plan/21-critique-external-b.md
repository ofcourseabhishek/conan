# Anonymous cross-critique — Reviewer: External B (alternative-design / research role), model "Pro"
Mapping (unknown to reviewer): A = External A, B = Claude Code, C = External B (this reviewer's own proposal, on Flash), D = External C.
Captured near-verbatim.

## Part 1
**A.** Strongest: page numbers decoupled from the LLM; char-offset map + RapidFuzz eliminates pagination hallucination.
Unsupported: in-process asyncio on Render free tier (spin-down kills memory-resident state). Coupling: synonym canonicalization
assumes uniform keys — brittle without schema enums. Unnecessary: json_repair ladder — response_schema guarantees JSON format.
Correctness: 10k-char batches may exceed output token limits or cause silent skipping of dense obligations. State: checkpoints
must flush to Neon immediately. Security: zero-width chars / adversarial text could bypass heading regex and manipulate the
prompt. Missing test: identical recurring clauses (notice terms on multiple pages) → wrong page. Simpler: map PyMuPDF blocks to
pages directly instead of a custom char-offset map.
**B.** Strongest: H19 freeze + SQLModel. Unsupported: **concurrency 4 will trigger 429 RESOURCE_EXHAUSTED on ~15 RPM Flash free
tier**. Coupling: weighted average dampens critical local risk (penalty 100 averaged with urgency 10). Unnecessary: Twilio trial.
Correctness: weighted float averages hard to explain → not reproducible from visible factors. State: resume needs locks around
Neon reconnections. Missing: band boundary tests (24.99 vs 25). Simpler: A's additive points table.
**C.** Strongest: client-side bundled demo bypasses Render cold start. Unsupported: LLM pages; per-pair D2 micro-prompts blow RPM.
Coupling: additive Σ parents inflates a node with three low-risk parents to max. Unnecessary: Kahn+Tarjan. State: fail-after-90s
guarantees failure on large contracts. Security: unprotected /demo/seed allows overwrites. Missing: cross-page clauses. Simpler:
enforce DAG at edge creation.
**D.** Strongest: reviewed-only propagation prevents hallucinated cascades; H12 freeze disciplined. Unsupported: BackgroundTasks
don't survive spin-down; per-clause calls hit 15 RPM. Correctness: fuzzy 0.8 too loose (boilerplate on wrong page). State: zombie
records. Security: unsanitized LLM text in toast (XSS if not escaped). Missing: 429 backoff test.

## Part 2 — red team / API realities
Most likely false: **response_schema effortlessly handles complex relational data** — large/deeply nested schemas or many enum
constraints frequently trigger 400 InvalidArgument / 500 errors (cites Google Cloud docs). Keep schemas flat and small.
429 mid-job: A retries; B/C/D drop data (concurrency, no backoff). Neon blip: uncommitted transactions → orphaned partial edges.
Render restart: in-memory checkpoints vanish unless persisted. Adversarial PDFs: scanned, multi-column, invisible text layers defeat
segmentation. Tests passing while wrong: **replay mode passes in CI while masking live 429 reality**. Silent wrong info: loose fuzzy →
wrong page; summation maxes out downstream nodes.
Free-tier realities (reviewer's claim, to verify at H0): Flash ≈ 15 RPM; concurrency/micro-prompts hit the ceiling in seconds;
application/json without strict schema risks malformed output; overly complex schema eats input tokens and risks 400s.

## Part 3
Fatal: C and D non-viable (call volume vs 15 RPM; in-memory/strict-timeout jobs on Render free).
**Rank A > B > D > C** (reviewer ranked its own proposal last, unknowingly).
Hybrid: A — offset mapping + RapidFuzz pages, additive risk, DB-persisted checkpoints; B — SQLModel, H19 freeze; C — client-side
bundled fixture (hidden combo) + JSONB for flexible state; D — propagation restricted to human-reviewed edges.
Top 5: (1) ~8k-char batches **run serially** (no concurrency/micro-prompts); (2) never ask LLM for pages — backend fuzzy-matches
quote to block offsets; (3) every batch result flushes to Neon immediately; (4) additive capped points (averages mask, sums explode);
(5) client-side mock data to evade cold start.
Would change mind: if free-tier RPM rose to ~1000, per-clause extraction (D) would win on accuracy/isolation.
