# Claude Code — critique of A/C/D + rebuttal/revision of own proposal (B)

Written after reading External A and External C critiques; before External B's critique returned.

## Critique of others
- **A (External A)** is the most complete and its core invariant (server-derived pages from verified quote offsets; LLM never
  emits IDs/pages) is strictly better than mine, which verified evidence but still took page from the clause. Adopt.
  Concern: resilience machinery (5-rung ladder, heartbeat + resume + lease) is ~3–4h of Person A's time that the demo may never
  exercise — both critics flagged this. External A's own critique proposes the cheaper equivalent: **memoize LLM calls by
  hash(model+prompt+schema) in Postgres**; a restart simply re-runs the job and completed batches are free cache hits. That removes
  heartbeat/lease/resume entirely. Adopt.
  Synonym-map event canonicalization is a real hazard (false merges → cascaded wrong dates). A **fixed event enum + "other:<label>"**
  is both simpler and safer. Adopt.
- **C (External B)**: /health pre-warm on landing is cheap and good. LLM-supplied pages and additive Σ-parent propagation are
  disqualifying as written (both critics agree). Log-scaled amount is a nice points tier.
- **D (External C)**: the only proposal with a serious rehearsal block; propagation over reviewed-only edges is the safest
  semantics but yields an empty demo unless edges are pre-confirmed. Per-clause calls are not viable on free tier.

## Objections against B (mine) and response
1. *Weighted average compresses severe single factors (overdue+blocked ≈45 "medium"); upstream capped at 20 pts makes the
   headline feature barely visible.* — **Concede.** Switch to additive capped points (A's table) with propagation up to 30 pts.
2. *upstream = max parent_risk·0.7^hop compounds (parent risk already includes its upstream).* — **Concede.** Propagate from the
   source's **base** score / state, not its effective score; take max over paths.
3. *Unverified edges propagation unspecified.* — **Revise:** unverified edges never propagate; proposed-but-verified edges do by
   default; "reviewed only" toggle.
4. *~6k-token batches risk output-token truncation.* — **Partially defend, revise:** input ~8–10k chars is fine; the risk is
   output length on dense clauses. Set max_output_tokens high, and on MAX_TOKENS finish-reason split the batch (A's ladder step).
   Batch size is a config value tuned by the eval at H8.
5. *Twilio at H17–19 is scope creep; trial only sends to verified numbers.* — **Concede.** SMS is simulated and labeled. Email is one
   real "send test reminder" to the requester's own typed address, rate-limited (not an open relay).
6. *create_all can't alter tables; losing cached demo rows.* — **Defend with mitigation:** schema changes during a hackathon are
   handled by drop + `seed_demo.py` re-import from the committed fixture; the demo cache is re-seedable by design.

## Revised B (converges on the hybrid)
Adopts A's page/ID invariant, evidence normalization, rule edges, points table, max-over-paths propagation; replaces resume with
LLM memoization; fixed event enum; H16 freeze. Keeps SQLModel/create_all + seed script, deterministic-first conflicts, and
concurrency 2 with Retry-After.
