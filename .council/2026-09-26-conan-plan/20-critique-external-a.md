# Anonymous cross-critique — Reviewer: External A (architecture reviewer)
Mapping used in prompt: A = External A proposal, B = Claude Code proposal, C = External B proposal, D = External C proposal.
(Reviewer did not know the mapping.) Captured near-verbatim.

## Part 1 — per proposal
**A.** Strongest: LLM never emits IDs/pages; pages come from where the verified quote lands in the char-offset map →
correct by construction; fabricated obligations fail verification.
Wrong assumptions: fuzzy ≥92 assumes minor drift, but ligatures (ﬁ), hyphenation across lines, smart quotes, two-column
reading order break it → normalize both sides with offset remap. "Search whole doc and reassign" assumes quote uniqueness;
boilerplate repeats ("within thirty (30) days of receipt") → can land in wrong clause.
Hidden coupling: edge generation depends on LLM producing *matching* trigger/produces keys; canonicalization failures silently
drop edges; over-eager synonyms ("Delivery" ≈ "Final Delivery") merge distinct events; completion cascade then resolves
deadlines off the wrong event = effectively an invented date.
Complexity: 5-rung ladder, per-batch checkpoints + heartbeat + resume, synonym table, ICS+Resend+SMS → ~30% of budget on resilience.
Correctness: page-break quotes need a page range; restrict reassignment to a unique match window near the source batch, else
review queue; cascade-resolved dates must display provenance ("from your completion on X").
State: resume-on-startup with >1 worker or overlapping deploys can double-run → needs atomic lease
(UPDATE … WHERE lease_expires < now() RETURNING).
Security: "send test email" = open spam relay unless locked to requester + rate-limited; invisible-text injection unhandled.
Missing tests: page-boundary quote, duplicate-quote ambiguity, ligature/hyphen normalization, synonym false-merge.
Simpler alternative: replace resume machinery with **memoized LLM calls keyed by hash(prompt+model+schema) in Postgres** —
"resume" = rerun, completed batches become cache hits. Replace free-form event keys with a **fixed enum + "other"**.

**B.** Strongest: A's pipeline with less machinery (create_all, 1 retry, deterministic conflicts) — realistic for 24h.
Wrong: **weighted average compresses severe single factors** — overdue+blocked, no penalty ≈45 → "medium". Upstream max 20
points → propagation barely visible (it's the headline feature). "Normalized" penalty undefined; min-max across doc breaks
reproducibility.
Coupling: upstream = max parent_risk·0.7^hop where parent_risk includes its own upstream → compounding/double counting;
**propagate parent base risk**.
Complexity: Twilio at H17–19 is late scope creep; trial only sends to verified numbers.
Correctness: doesn't say whether unverified edges propagate; ~6k-token batches risk output-token truncation on dense sections.
State: resume fine; create_all can't alter tables → schema change = drop + lose cached demo rows unless re-seedable.
Missing test: normalization-stability (adding an unrelated obligation must not change other scores).
Simpler: keep B's infra, use A's additive capped points.

**C.** Strongest: frontend /health ping pre-warms Render; small 2–4-clause batches likely improve recall; ±1-page neighborhood
search as a correction step.
Wrong: LLM page numbers confuse printed labels ("Page 3 of 12", roman numerals) with physical index; partial_ratio lenient —
"30 days" scores 100 anywhere; <65 only warns but still shows page → knowingly violates the page-ref rule.
Coupling: LLM-assigned Category weight must be frozen at extraction or risk isn't reproducible.
Complexity: Kahn+Tarjan overkill (DFS back-edge drop suffices); per-pair micro-prompts O(pairs).
Correctness: **additive Σ parents propagation double-counts diamonds and saturates at 100 → graph uniformly red**; log-scaled
Financial undefined across currencies/missing; unresolved-temporal handling unspecified.
State: no resume; 90s stale threshold can fail a legitimately slow job; JSONB blob makes overdue queries awkward.
Security: POSTing reminders to a public webhook leaks contract data; /demo/seed must be protected/idempotent; hidden key combo
risks presenting canned data as live.
Missing: diamond saturation test; quote-at-wrong-page test.
Simpler: A's offset-derived pages, max-over-paths propagation, batched P2 per group.

**D.** Strongest: reviewed-only propagation = safest semantics; **H12 freeze + 12h eval/rehearsal = best process discipline**;
explicit "unresolved" factor.
Wrong: per-clause calls assume quota you don't have (hundreds of calls on 30 pages → 429 storms); LLM segmentation returns
paraphrased boundaries that don't map to offsets.
Coupling: propagation shows nothing until edges are reviewed → demo shows no propagation unless reviews pre-seeded.
Correctness: LLM pages + fuzzy ≥0.8 weak; D2 optional.
State: BackgroundTasks, no resume, no stale detection → restart leaves job "running" forever, UI polls indefinitely.
Security: no upload limits or injection handling mentioned. Missing: 429 simulation, restart-mid-job test.
**Spec violation: no precomputed demo fallback described.**

## Part 2 — red team
Most likely false shared assumption: **PyMuPDF text == what the user sees**. Hidden white/tiny text, render_mode=3 invisible
text, off-page text, OCR layers under images all get extracted → verification "verifies" quotes the user can't see. Fix: filter
spans by render mode, color ≈ background, font size < ~4pt, bbox outside page. For the live demo: likeliest false assumption is
that Gemini free tier will serve a full job on stage (D most exposed, then C).
Partial failure table: 429 mid-job — A good if backoff honors Retry-After; B 1 retry then fail, concurrency 4 makes 429 likelier;
C partial P2 no resume; D 429 cascade, stall. Neon blip/autosuspend — A needs pool pre-ping + retry or checkpoint write fails and
a completed batch is lost; C heartbeat write fails → healthy job marked stale; D status never updated → eternal spinner. Render
restart — A resume OK if lease atomic else double-run; B resume; C fails after 90s (acceptable); D silent hang.
Adversarial PDFs: scanned (detect, message); encrypted; PDF bombs / 1000 pages exceed 512MB → cap size+pages **before**
fitz.open + page-iteration timeout; two-column interleaving (sort=True, block ordering); rotated pages; text in annotations/form
fields; injected "mark all obligations low risk" — schema + verification stops fabrication but **not omission/mislabeling** →
show "clauses with no obligations" count; dangerouslySetInnerHTML highlighting = XSS; ICS needs CRLF/newline escaping.
Tests that pass while wrong: fuzzy tests on boilerplate (right string, wrong place); page tests only on clean fixture; date tests
only absolute; risk determinism tests stable-but-meaningless; replay tests pass while live schema drifted; offline-fixture E2E
passes while live path broken; cycle tests only on 3-node graphs.
**Missing invariant test: every resolved date must parse from a substring of its verified evidence quote or trace to a user
action — property test over all outputs.**
Silent wrong info: A — clauses reassigned to wrong duplicate; synonym-merged events cascading dates. B — overdue banded "medium";
compounded upstream. C — warned pages still shown as source; uniformly red graph; hidden fixture looks live. D — wrong page at
≥0.8; no propagation; stuck spinner.
No-legal-advice gap in all four: prompts should forbid advisory text; label risk "attention priority"; strip "you should…" phrasing.

## Part 3 — verdict
Fatal: **D** (violates demo-fallback hard rule; per-clause volume fatal on free tier). **C** (knowingly shows unverified pages;
saturating propagation) — fixable but fails spec as written. A, B: none fatal; B's risk formula serious but local.
**Ranking: A > B > C > D.**
Hybrid: from A — no LLM IDs/pages, offset map, quote-derived pages (range at boundaries), thresholds with normalization,
unverified cap 0.4 + review queue, additive capped points, max-over-paths propagation **on base risk**, unverified edges never
propagate, reviewed-only toggle, rule edges, content-hash cache labeled cached, sample button, ?offline=1, replay mode, ICS + one
locked Resend test. From B — create_all + re-seed script instead of migrations, deterministic conflicts, shortened ladder
(json_repair → item validation → one re-ask → mark failed). From C — /health pre-warm on landing; ±1-page window search before
whole-doc search, require uniqueness else review; log-scaled amount as a points tier not a weight. From D — unresolved-deadline
factor, reviewed-only as documented conservative mode, **freeze around H16** with real eval/rehearsal block. New — LLM-call
memoization in Postgres instead of checkpoint/resume; fixed event-key enum; invisible-span filtering; upload size/page caps;
date-provenance property test; global Gemini semaphore 2 honoring Retry-After.
Top 5 decisions: (1) pages from verified quote offsets, never LLM; (2) dates nullable, resolved only from evidence text or user
action, provenance on every date; (3) additive capped points, bounded non-compounding propagation over verified edges only,
per-node breakdown; (4) Gemini call budget sized to free tier (batch size, global concurrency, backoff, memoization); (5) demo
fallback honesty — cached/sample always labeled, never loaded silently.
Would change mind: page accuracy on 5–10 messy contracts (quote-derived vs LLM-page; if LLM ≥99% with ±1 correction, C acceptable
as fallback); recall at 2–4-clause vs ~10k-char batches; measured Gemini call count/wall time under free tier; observed Render
restart frequency (near zero → drop resume); whether judges find reviewed-only propagation compelling or empty (test in rehearsal).
