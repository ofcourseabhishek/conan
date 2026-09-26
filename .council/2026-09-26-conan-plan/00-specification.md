# Council Specification — "Conan" (AI contract obligation & risk intelligence), 24h hackathon plan

## Objective

Produce the final, executable implementation plan for **Conan**, a web app that turns a contract PDF into a
source-linked, reviewable set of obligations (who must do what, by when, under which condition, with what
consequence), connects them in an **obligation dependency graph**, and flags **explainable risk** —
including "potential downstream impact" when an upstream obligation is blocked/late.

It must be built by **2 developers in 24 hours** and demoed live to judges (3-minute story).

Core journey: upload PDF → page-indexed text → clause segmentation → obligation extraction → schema
validation → temporal normalization → dependency edges → risk scoring → human review → timeline + graph.

Positioning: NOT "chat with your PDF", NOT an AI lawyer. It is a review/tracking aid; it never gives legal
advice or decides which conflicting clause legally prevails.

## Requirements

MVP (must work end-to-end):
1. Upload a text-based PDF; validate type/size; show processing state and useful errors.
2. Extract text with page numbers and section context.
3. Segment clauses; categorize (payment, renewal, termination, compliance, delivery, penalty, confidentiality, other).
4. Extract obligations: actor, action, object, trigger, deadline_rule (absolute / relative-to-trigger / recurring / none),
   amount, penalty, evidence quote, clause/page reference, confidence.
5. Human review: confirm / edit / reject extracted obligations; audit trail of edits.
6. Obligation list with filters (category, party, status, due date, risk band).
7. Transparent risk explanation (factor breakdown, no unexplained scores).
8. Every obligation links to its source clause + page (click-through to evidence).
9. Deadline timeline + interactive obligation graph (graph is the centerpiece).

Differentiators (in priority order, after MVP):
- D1: Dependency risk propagation — when an obligation is blocked/overdue/unresolved, flag downstream
  obligations with "potential downstream impact" and show the evidence for each edge.
- D2: Potential clause conflict detection within a contract (inconsistent dates/amounts/terms) — flag for review only.

Stretch (in order, only after MVP + D1 + D2): email + SMS deadline reminders; ICS/CSV calendar export;
contract version comparison (material obligation changes); multi-contract overview. OCR is out of scope.

## Non-goals

Legal advice, enforceability, precedence between conflicting clauses; training models; enterprise DMS,
complex permissions/multi-tenant auth; a free-form chatbot; OCR of scanned PDFs.

## Existing relevant architecture

Greenfield — empty git repo. Decided stack (team is comfortable with it; not up for debate unless there is a fatal flaw):
- Frontend: React + Vite + Tailwind, React Flow for the graph, Recharts optional. Hosted on Vercel.
- Backend: Python FastAPI, PyMuPDF for PDF text, Pydantic for validation. Hosted on Render (free/cheap tier; beware cold starts, ~512MB RAM).
- LLM: Google Gemini API (structured JSON output / response schema). Free-tier rate limits apply.
- DB: hosted Postgres (Neon or Supabase free tier).
- Analysis runs as an async job; the UI polls job status with progress stages.
- LLM runs in TWO passes: pass 1 extracts obligations per clause chunk; pass 2 takes all extracted obligations
  (compact form) and proposes dependency edges (depends_on / must_precede / condition_for / may_trigger) with evidence.

Team split: Person A = PDF ingest, Gemini extraction, validation, FastAPI, DB, risk engine.
Person B = React UI, review screens, timeline, React Flow graph, deploy of frontend, demo/pitch.

Demo data: a hand-crafted fictional vendor/service agreement (~6–10 pages) with planted dependencies,
relative deadlines ("within 30 days of invoice receipt"), a penalty clause and one planted conflict; plus a few
public contracts from the CUAD dataset to show generalization.
Evaluation: hand-labeled gold set of 10–20 obligations from the demo contract + pytest scoring script
(obligation precision/recall, field accuracy, evidence correctness, date normalization).

## Constraints

### Technical
- 24 wall-clock hours, 2 people, including deploy, pitch, and rehearsal.
- Gemini free-tier rate limits / latency; a 10-page contract may be 30–60 clauses.
- Render free tier: cold starts, ephemeral disk, limited RAM, background work must survive within the web process
  (no separate worker unless justified).
- Must never invent calendar dates: if a relative deadline's trigger date is unknown, due_date stays null and the item is
  "date unresolved" until the user supplies the trigger event date.
- Keep extracted facts, computed values, and AI-generated explanations distinguishable in data and UI.

### Security / privacy
- API keys server-side only. Validate uploads (magic bytes, size, page cap). Don't log full contract text.
- Use fictional/public contracts only. Provide delete. Disclaimer: extraction can be wrong; requires human verification.
- Prompt-injection risk: contract text is untrusted input to the LLM.

### Performance / reliability
- Demo contract end-to-end analysis ideally < 60–90s; UI must show progress.
- Must degrade gracefully: malformed LLM JSON, empty extraction, API quota errors, PDF with no text layer.
- A precomputed known-good analysis of the demo contract must be available as a fallback (seed/cache).

### Compatibility
- Single repo (monorepo: /backend, /frontend). Shared API contract agreed at hour 0–1.

## Success criteria
- A judge can upload the sample contract on the hosted URL and reach the obligation list + graph with no developer help.
- ≥ 80% of gold obligations found; every displayed obligation has a correct page reference; zero invented dates.
- Risk flags are reproducible from visible factors.
- Graph shows at least one evidence-backed dependency chain and downstream-impact highlighting.
- Rehearsed 3-minute demo with offline fallback (recording/screenshots).

## Edge cases
- Relative deadlines with unknown trigger; business days vs calendar days; recurring obligations ("monthly", "each quarter").
- Cross-references ("subject to Section 7.2"); defined terms ("the Services", "Effective Date").
- One clause yielding multiple obligations; obligations split across page breaks.
- Duplicate obligations extracted from overlapping chunks.
- Dependency cycles proposed by the LLM; edges referencing non-existent obligation IDs.
- Mutual obligations (both parties); conditional obligations that may never trigger.
- Scanned PDF (no text) → clear error. Very long PDF → page cap.

## Likely affected files/modules
backend/: app/main.py, api/ (contracts, obligations, graph, timeline), services/ (pdf_ingest, segmenter, llm_extract,
validate, temporal, dependencies, conflicts, risk, jobs), models/ (SQLAlchemy/SQLModel + Pydantic schemas),
prompts/, tests/ (gold set + scoring), seed/.
frontend/: pages (Upload, Overview, Obligations, ObligationDetail, Graph, RiskTimeline), api client, components.

## Questions the council must resolve
1. Clause segmentation: regex/heading heuristics on PyMuPDF blocks vs. LLM-based segmentation vs. hybrid? How to preserve page spans?
2. Pass-1 chunking: per clause, or batched clauses per call (to respect rate limits)? Concurrency level? Retry/repair strategy for invalid JSON?
3. Pass-2 dependency proposal: how to bound it (N obligations → edges), validate edges (IDs exist, evidence quote actually appears in source, cycle handling), and label them "proposed until reviewed"?
4. Evidence verification: how to check an evidence quote really appears in the cited page (fuzzy match threshold)?
5. Temporal model: exact deadline_rule schema; how trigger events become user-settable "events" that resolve many dates at once.
6. Risk formula: concrete factors, weights, bands, and how propagation works (decay per hop? max depth? only through reviewed edges?).
7. Conflict detection (D2): simplest approach that produces credible flags in ~2 hours.
8. Async jobs on Render: FastAPI BackgroundTasks vs. in-process asyncio task vs. a real queue? What happens if the instance restarts mid-job?
9. Data model: Postgres tables vs. storing the analysis as JSONB blobs + a few tables? Migration tooling or not?
10. Hour-by-hour plan for 2 people with explicit integration checkpoints, a cut-list, and when to freeze features.
11. Where are the reminder features (email/SMS) cheapest to add, and should they be faked for the demo?
12. What is the single biggest risk to a working live demo and how do we neutralize it?

## Sanitization notes
Safe to share externally: this entire specification. The repo is empty; no secrets, customer data, or proprietary code exist.
Team member names are omitted.
