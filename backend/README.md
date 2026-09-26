# Conan backend (Person A)

FastAPI + PyMuPDF + Gemini + Postgres. Spec: [docs/TRD.md](../docs/TRD.md). Plan: the council build plan.

## Run locally

```bash
cd backend
uv venv .venv --python 3.11
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
cp .env.example .env          # leave DATABASE_URL empty for local SQLite
.venv/Scripts/python -m uvicorn main:app --reload --port 8000   # or app.main:app
.venv/Scripts/python -m pytest -q
```

## For Person B (frontend)

- **Types:** `frontend/src/types/api.ts` is generated from `app/schemas.py`. Never edit it by hand; run
  `.venv/Scripts/python scripts/export_types.py` after any schema change and commit both files.
- **Fixture:** `frontend/public/offline_fixture.json` (same as `backend/fixtures/demo_analysis.json`) is a
  full `Analysis` with 4 obligations (O-004 → O-007 → O-009 → O-012), 3 edges, 4 events, 1 conflict and an
  audit trail. Offsets and pages are real, so quote highlighting works: highlight
  `clause.text.slice(o.evidence_start - clause.char_start, o.evidence_end - clause.char_start)`.
  Regenerate with `scripts/make_fixture.py`.
- **Live today:** `GET /api/health`, `POST /api/contracts` (multipart `file`), `GET /api/jobs/{id}`,
  `GET /api/contracts/{id}/analysis?as_of=&reviewed_only=`, `DELETE /api/contracts/{id}`, and the mutations below.
  Every mutation accepts `?as_of=&reviewed_only=` and returns the full updated `Analysis` (replace your cache entry):
  - `PUT /api/contracts/{id}/events/{key}` `{date: "YYYY-MM-DD" | null}` — resolves every obligation waiting on it
  - `PATCH /api/obligations/{id}?contract_id=` `{action: confirm|edit|reject, patch?, note?}`
  - `PATCH /api/obligations/{id}/status?contract_id=` `{status, occurred_on?}` — `done` sets the event the
    obligation produces (completion cascade); moving back to `open` un-sets it. Use `blocked` for "Simulate blocked".
  - `PATCH /api/edges/{id}` `{action: confirm|reject}`
- Edges: `source` is `rule` (deterministic) or `llm` (P2). Draw `proposed` dashed, `confirmed` solid; hide
  `rejected` / `auto_rejected` and, by default, `evidence_status: "unverified"`. `propagates` says whether the
  edge feeds downstream impact under the current `reviewed_only`.
- Events for `other` triggers are keyed `other:<obligation id>` and never merge.
- A finished job with some failed clauses is `done_with_warnings` with `error_code: "PARTIAL_EXTRACTION"`;
  those clauses have `extraction_state: "extraction_failed"`.
- **Errors** are `{error_code, message, action}` (see `app/errors.py`); failed jobs carry `error_code`,
  `error_message`, `error_action`.

## Multiple Gemini keys

Set `GEMINI_API_KEY` and optionally `GEMINI_API_KEYS=key2,key3` (comma-separated; duplicates ignored). All keys
are used together:
- each key has its own `GEMINI_RPM` limiter, so throughput scales with the number of keys;
- a per-minute 429 cools that key down and the call moves straight to another key;
- a daily-quota 429 parks that key until Gemini's reset (midnight Pacific) and the rest carry on;
- only when every key is out for the day does a job fail with `LLM_QUOTA`.
Cached responses are shared across keys. Keys are never logged (logs say `api_key=#2`); `/api/health` reports
`llm_keys_total` / `llm_keys_available` only. `scripts/gemini_smoke.py` checks every key.

Note: keys from the same Google Cloud project share that project's quota, so extra keys only add capacity if they
come from different projects.

## H0 checks (council conditions)

1. Put your key in `backend/.env`, then `.venv/Scripts/python scripts/gemini_smoke.py` confirms the model id and the
   flat P1 schema. Read RPM/RPD for that model off the AI Studio rate-limit page and set `GEMINI_RPM`.
2. Render: New → Blueprint → this repo (`render.yaml`). Set `DATABASE_URL` (Neon, `sslmode=require`),
   `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_RPM`, `ALLOWED_ORIGINS` (Vercel URL).

## Status

| Stage | Module | State |
|---|---|---|
| Upload validation, ingest, invisible-span filter, offset map, header/footer strip | `pipeline/ingest.py` | done, tested |
| Segmentation, parties, glossary | `pipeline/segment.py` | done, tested |
| Gemini client: token bucket, backoff, `llm_cache`, replay | `pipeline/gemini.py` | done, tested (fake transport) |
| Job runner, stale-job requeue | `pipeline/runner.py` | stages 1–4 wired |
| P1 prompt + repair ladder | `prompts/p1_system.txt`, `pipeline/extract.py` | done, tested (fake transport) |
| Evidence verifier, derived pages | `pipeline/verify.py` | done, tested |
| Actor canonicalization, dedupe, IDs | `pipeline/dedupe.py` | done, tested |
| Risk + propagation (pulled forward from H9) | `pipeline/risk.py` | done, tested; fixture scores match |
| Eval scorer | `tests/eval_score.py` | done; run #1 needs a live key + B's `fixtures/gold.json` |
| Dates, events, completion cascade, recompute | `pipeline/temporal.py`, `pipeline/recompute.py` | done, tested (+ property tests) |
| Review / status / event / edge endpoints, audit trail | `api/review.py` | done, tested |
| Rule edges (event chain, cross-ref, penalty), P2 + validation, cycle breaking, rule refresh on edit | `pipeline/edges.py`, `prompts/p2_system.txt` | done, tested; CP3 story rehearsed in `test_demo_story_end_to_end` |
