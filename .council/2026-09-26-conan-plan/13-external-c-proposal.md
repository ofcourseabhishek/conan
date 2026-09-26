# External C — Independent Proposal (captured)

> Capture note: response was cut off by the provider mid-"Performance" section (output limit on the fast model).
> Everything up to that point is condensed below; nothing after "Performance: Target <60–90 s for 6–10 page demo.
> Parallelism limited" exists.

## Executive summary
Focused 24h MVP: page-indexed text → clauses → two-pass Gemini (obligations, then edges) → validate/normalize → Postgres →
review with audit → filterable list, transparent risk, source-linked timeline, React Flow graph centerpiece. D1 included;
**D2 is a thin post-process only if time remains**. Precomputed known-good analysis of the demo contract is the safety net.

## Architecture
Monorepo. FastAPI on Render: endpoints for upload, job status, review, list/filter, graph, delete. **BackgroundTasks /
in-process asyncio** runs the pipeline; status in Postgres. React SPA on Vercel polls /jobs/{id} every 2–3s. Neon tables:
jobs, documents, clauses, obligations, edges, reviews, audit. Extracted facts / computed values / explanations labeled
distinctly in DB and API responses.

## Components
UploadService (magic bytes, size ≤10MB, page cap ~30, temp storage on ephemeral disk or base64 in job row); TextExtractor
(PyMuPDF → [{page, text, blocks}]); ClauseSegmenter (hybrid) → {clause_id, page_start, page_end, text, category_hint};
ObligationExtractor (P1); DependencyProposer (P2); Validator/Normalizer (Pydantic, temporal rules, fuzzy evidence, cycle
detection); RiskEngine (pure functions over reviewed obligations + edges); ReviewAPI (PATCH confirm/edit/reject + audit
row); GraphAPI (nodes/edges; proposed labeled). Frontend: UploadPage, JobProgress, ObligationList, ReviewModal, Timeline
(Gantt-like), GraphView, Disclaimer footer.
Schemas: DeadlineRule{kind absolute|relative_to_trigger|recurring|none, absolute_date, relative_days, relative_unit
calendar|business, **trigger_event_id** (links to user-settable event), recurrence "monthly"}; Obligation{id, actor, action,
object, trigger, deadline_rule, amount, penalty, category enum, evidence_quote, **page (int, from LLM)**, clause_id,
confidence, status proposed|confirmed|edited|rejected, due_date (never invented), risk_score, risk_factors}; Edge{id,
from_id, to_id, relation enum, evidence…}.

## Flow
POST /upload → validate → Job queued → BackgroundTasks pipeline: extract_text → segment → pass1_extract →
validate_normalize → pass2_edges → risk → ready. Poll shows stage + errors. Review PATCH → audit → recompute risk/graph.
Trigger events: user sets date → resolves all referencing relative deadlines in one transaction. Delete: soft-delete →
cascade hard-delete after 24h.

## Council answers
Q1 Hybrid: PyMuPDF block/line + regex/heading heuristics (numbered, ALL-CAPS, "Section X", bold via font flags). **Fallback
for long unstructured blocks: single Gemini call on the page text "split into clauses preserving page spans"**. Preserve
page_start/page_end and char offsets.
Q2 **Per-clause (or 1–2 short clauses)** to keep context tight; Semaphore(3); invalid JSON → one "repair to match schema"
retry → drop chunk + partial warning; response_schema + Pydantic.
Q3 Compact list (id, actor, action, deadline summary, clause_id, page), never full text; validate IDs, fuzzy evidence vs source
clause, self-loops, DFS/topo cycle drop + log; all edges proposed (dashed) "AI-proposed dependency — review required".
Q4 Normalize (lower, ws, strip punct); rapidfuzz.partial_ratio or SequenceMatcher **≥0.8**; fail → evidence_verified=False,
lower confidence, warning; page must match cited page or adjacent.
Q5 As schema; absolute due_date set immediately; relative null until user sets TriggerEvent(id, name, date) → UPDATE all
obligations with matching trigger_event_id; recurring shows next occurrence after trigger resolved; business days skip
Sat/Sun, no holidays.
Q6 Base (0–100) = 0.30·late_or_blocked + 0.25·penalty_present + 0.20·high_amount_or_critical_category + 0.15·low_confidence
+ 0.10·unresolved_date. Propagation (D1) **only along confirmed/reviewed edges** of type depends_on/must_precede/condition_for:
if upstream blocked/overdue/unresolved add 0.6 × upstream_risk × 0.7^hop, max depth 3. Final min(100, base + propagated).
Bands 0–30 low, 31–60 medium, 61–100 high. Explanation = factor dict + contributing upstream edges with evidence; recompute on
every review change.
Q7 After P1 group by (actor, action_normalized, object); flag conflicting absolute dates, amounts, mutually exclusive
categories (terminate vs auto-renew on same trigger); regex numeric scan; "possible inconsistency — human review" with both
quotes; no resolution.
Q8 BackgroundTasks/asyncio; state in Postgres; restart → job left at last stage, UI shows "interrupted — re-upload or use
demo"; pre-seed completed demo job. No Redis.
Q9 Normalized tables (jobs, documents, clauses, obligations, edges, trigger_events, reviews, optional users); JSONB only for
risk_factors and raw Gemini response (debug). Alembic optional; create_all / manual schema.
Q10 H0–1 scaffold, Neon, deploy skeletons, shared types, sample PDF + gold set. H1–3 extract + segment + upload / progress +
list; **CP H3**. H3–6 P1 + validation + temporal + evidence / review modal + audit + filters; **CP H6 E2E extract**. H6–9 P2 +
cycle/evidence validation + risk + propagation / timeline + graph + highlighting; **CP H9 planted chain visible**. H9–12
conflicts (if time), delete, error paths, precomputed demo job / polish, disclaimer, offline toggle. **Feature freeze H12**.
H12–16 integration, eval script, bug fixes, deploy. H16–20 demo script, rehearsal ×3, hardening, slides. H20–24 polish, sleep
buffer, fallback verification. Cut order: conflicts → recurring → advanced business-day calendar → SMS → multi-contract.
Q11 Skip real delivery; "Reminder scheduled (demo)" toast + log event. Later: Resend / Twilio trial + reminder rows + cron-like
poll.
Q12 Gemini free-tier rate limit / cold start / malformed JSON mid-demo. Neutralize: (1) precomputed known-good job in DB with
one-click "Load demo analysis"; (2) locally cached Gemini responses for the sample; (3) visible progress + "partial results —
review what we have"; (4) offline mode that never calls Gemini.

## Dependencies
fastapi, uvicorn, pymupdf, pydantic, google-generativeai, sqlalchemy, asyncpg/psycopg, rapidfuzz, python-multipart, alembic
(optional). react, vite, tailwind, @xyflow/react, date-fns, react-query or fetch. No OCR, no queues.

## Failure modes
No-text → 400 "text-based PDF required"; page cap → reject; quota/timeout → stage failed, keep partial, offer demo; invalid
JSON → retry once then skip; bad edge → drop + log; restart → job stays at last stage, offer re-run/demo; empty → message +
demo; evidence fail → flag + lower confidence. Never invent dates or silently drop.

## Security/privacy
Magic bytes/size/page count; keys in Render env; contract text never logged (IDs/metadata only); fictional/public only; delete
endpoint; 24h retention note; disclaimer every page ("Not legal advice. Human review required. AI may err."); no auth
(single-tenant demo); CORS locked to Vercel.

## Performance
"Target <60–90 s for 6–10 page demo. Parallelism limited" — [response truncated here by provider].

## Sections missing due to truncation
Migration/rollback, testing strategy (beyond gold script mention), main tradeoffs, strongest argument against, confidence.
