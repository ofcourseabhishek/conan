# External B — Independent Proposal (captured)

> Capture note: condensed faithfully from the provider response (~20k chars); all concrete numbers, schemas and decisions kept.

## Executive summary
"Radical reliability over algorithmic extravagance": zero hallucinated dates via dual-state relative temporal model with
user-settable anchor events; deterministic risk engine decoupled from extraction, propagating down a DAG with edge-weight
decay; **dual-mode hydration** — live async pipeline plus pre-baked seeded fixtures for instant recovery.

## Architecture
Vercel SPA (React 18, Vite, Tailwind, React Flow custom SVG nodes colored by risk, badged by review status) → FastAPI on
Render (single worker, in-process async worker, magic-byte validator, deterministic risk calc) → PyMuPDF block extraction +
Gemini ("gemini-1.5-flash", JSON mode) P1 extract / P2 dependency DAG → Neon Postgres (normalized documents, clauses,
obligations, dependencies, triggers + indexed JSONB).

## Interfaces (/api/v1)
POST /documents/upload (magic %PDF-, ≤10MB, ≤25 pages) → 202 {document_id, job_id}; GET /jobs/{id} {status enum: queued,
extracting_text, parsing_clauses, extracting_obligations, mapping_dependencies, scoring_risk, complete, failed; progress_pct;
error}; GET /documents/{id}/graph; PATCH /obligations/{id} (confirmed/edited/rejected, custom trigger dates, field edits,
audit); **POST /documents/{id}/triggers/resolve {trigger_name, resolved_date}** → recompute dependent deadlines; GET
/documents/{id}/export/{ics|csv}; **POST /demo/seed** hydrates pre-parsed golden records in <200ms bypassing LLM.
Components: PDFStructuralExtractor, GeminiClient (token bucket, concurrency 3, **15s timeout per chunk**, backoff),
VerificationEngine (Levenshtein fuzzy), RiskEngine (Kahn topological sort).

## Flow
Upload → validate (>50 chars/page avg) → persist QUEUED → create_task → segmentation → P1 (batch 2–3 clauses, ~1.5k
tokens) → grounding (fuzzy match ≥0.85 verified else grounding_warning) → P2 (compact {id, actor, action, trigger}) → prune
bad IDs, drop cycle back-edges → risk → persist COMPLETE → UI polls → graph/timeline/list; trigger date input recomputes;
review recomputes risk.

## Schemas
DeadlineRule{rule_type: absolute|relative_to_trigger|recurring|unspecified; target_date; offset_days; anchor_event;
day_type calendar|business (default calendar); recurrence_interval daily..annually}.
ObligationExtraction{temp_id "OBL-1", actor, action, target_object, category enum, trigger_condition, deadline,
financial_amount float, penalty_description, evidence_quote, **page_number (1-based, LLM-provided)**, confidence}.
DependencyEdgeProposal{source_id, target_id, relationship must_precede|condition_for|may_trigger, rationale, evidence_quote}.

## Risk formula
R_base = min(100, 0.25·C + 0.25·F + 0.30·T + 0.20·P).
C category: penalty 90, termination 85, payment 75, delivery 70, compliance 50, confidentiality 40, renewal 30, other 20.
F financial: null→10 else min(100, (log10(max(100,amount))−2)/3 ×100) ($1k≈33, $10k≈66, $100k+=100).
T temporal: overdue 100, unresolved relative trigger 70, due ≤7d 60, ≤30d 30, completed 0.
P penalty: explicit LD/forfeiture 100 else 0.
Propagation: R_eff(v) = min(100, R_base(v) + Σ_parents γ·R_eff(u)·I(u)), γ=0.5 per hop, max depth 3;
I(u)=1.0 overdue/rejected/unfulfilled, 0.5 unanchored trigger, 0 confirmed/satisfied. In Q6 also: proposed edges carry
extra 0.7× discount; propagate over both proposed and confirmed edges.
Bands: High ≥70, Medium 40–69, Low <40. Tooltip breakdown e.g. "Base 42 (Payment 25, Financial 17) + Upstream spillover
36 from OBL-2 (Overdue Delivery, 2 hops)".
Cycle breaking: Kahn; if stuck, Tarjan SCC; delete lowest-confidence back-edge; UI warning graph_cycle_pruned.

## Dependencies
fastapi, uvicorn, pydantic 2, **google-generativeai 0.4.1**, pymupdf, python-multipart, psycopg[binary,pool], python-dotenv,
rapidfuzz, pytest, pytest-asyncio. Frontend: react 18, reactflow 11, lucide-react, clsx, tailwind-merge, canvas-confetti.

## Failure modes
429 → token bucket (15 RPM) + fixture fallback for known demo contracts. Malformed JSON → response_schema + json_repair or
flag chunk for manual review. Scanned → ≤50 chars/page avg → friendly banner. Render sleep → **frontend HEAD /health on
landing page load** to wake backend before the drop. OOM → 25 pages/10MB cap; page-by-page generator. Phantom edges →
filter by P1 ID set.

## Security/privacy
PDF bytes processed in memory / /tmp and deleted in finally (zero retention). `<untrusted_document_context>` tags.
Permanent disclaimer header/footer. Keys server-side only.

## Performance
~26s avg for 8 pages (parse 1.2s, P1 12–16s, verify 0.4s, P2 6–8s, risk+persist 0.8s); <180MB RAM; React Flow 50 nodes.

## Migration/rollback
No Alembic; db_init.py CREATE TABLE IF NOT EXISTS at startup; POST /admin/reset-db drops/recreates in dev. Tag stable-mvp;
frontend VITE_USE_FIXTURES=true turns client into fully static demo.

## Testing
Gold set 15 obligations; asserts recall ≥80%, category accuracy ≥85%, zero invented dates (relative triggers have
target_date None); grounding test partial token ratio ≥85 vs page text; cycle test A→B→C→A.

## Hour plan
0–2 joint setup (schemas, seed contract, repo, Neon); A FastAPI+DB+PyMuPDF; B Vite+Tailwind+React Flow shell. 2–6 A P1 +
parser + chunking; B dropzone, polling, table. **CP1 H6**. 6–10 A P2 + DAG validation + cycle breaking; B custom nodes +
auto layout. **CP2 H10**. 10–14 A risk + propagation + anchor resolution API; B review modal, trigger dialog, timeline.
**CP3 H14**. 14–17 D1 highlighter + D2; B conflict badges, chain highlight on hover. 17–19 ICS export + /demo/seed; B
filters, empty states, source drawer. **Freeze H19**; 19–21 deploy + eval harness; 21–24 pitch, rehearsal, fallback drills,
backup video. (No sleep scheduled.)
Cut list at H16: D2 entirely → ICS/CSV (window.print) → timeline Gantt (sort table by due_date).

## Council answers
Q1 hybrid: `get_text("blocks")`; heading = numbering regex `^(SECTION|ARTICLE|\d+(\.\d+)*)\s+` + larger font / bold flag +
short line (<80 chars, no period); clause accumulates blocks until next heading; start_page/end_page.
Q2 batch 2–4 adjacent clauses (~1.5–2k tokens), Semaphore(3), response_schema, json_repair, one retry at temp 0 with error,
else log extraction_error and continue.
Q3 P2 minified [{id, actor, action, trigger}] (<1k tokens for 25 obligations); referential filter; fuzzy verify quote
against combined text of the two clauses; Kahn cycle pruning lowest confidence; review_status proposed (dashed) →
confirmed (solid).
Q4 **LLM supplies page_number**; normalize (lower, ws, strip punctuation); partial_ratio vs that page ≥85 verified; 65–84 →
search page ±1 and correct page; <65 → grounding_warning badge.
Q5 trigger_events(id, document_id, event_name, resolved_date); P1 normalizes trigger strings to anchor keys; "Unresolved
Triggers" banner; resolve endpoint runs SQL update target = resolved + offset (business via numpy.busday_offset).
Q6 as above (0.5/hop, 3 hops, proposed edges ×0.7).
Q7 group by (category, actor); deterministic value collisions (amounts, notice periods); then a targeted micro-prompt per
suspect pair {is_conflict, description, confidence}; amber flags.
Q8 asyncio.create_task + jobs table (status, progress); **no resume** — on poll, processing with updated_at >90s → failed
"Server dyno recycled. Restart or load precomputed analysis".
Q9 hybrid: documents, clauses, obligations (core columns + data JSONB incl. temporal/financial/**audit logs**), dependencies,
trigger_events; no migrations; reset endpoint.
Q10 as plan; checkpoints H6/H10/H14/H19.
Q11 **simulate**: "Automate Reminder" toggle → real POST to a Webhook.site URL or Discord webhook + toast "Simulated SMS
queued…" + modal with payload. No Twilio/SendGrid.
Q12 LLM hang/API outage/cold start. Three-tier fail-safe: (1) HEAD /health on landing; (2) /demo/seed "Load Sample Contract"
button if live parsing stalls >15s; (3) bundled static fixture, Ctrl+Shift+F loads full interactive graph client-side.

## Tradeoffs
No OCR (saves ~400MB, OOM); batching vs whole-doc; in-process worker accepts that a restart aborts the active job.

## Strongest argument against (self)
Two-pass pipeline compounds latency and rate-limit exposure → stalled spinner on stage. Defense: dual-path demo (live mode with
step indicators + "Load Golden Sample" / hidden key combo).

## Confidence
9/10. Unresolved: Neon idle connection drops (pool_recycle=300, max_overflow=2); mutual obligations (prompt: one per actor).
