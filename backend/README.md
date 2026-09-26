# Conan backend (Person A)

FastAPI + PyMuPDF + Gemini + Postgres. Spec: [docs/TRD.md](../docs/TRD.md). Plan: the council build plan.

## Run locally

```bash
cd backend
uv venv .venv --python 3.11
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
cp .env.example .env          # leave DATABASE_URL empty for local SQLite
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
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
  `GET /api/contracts/{id}/analysis?as_of=&reviewed_only=` (clauses, obligations with risk; no events/edges yet),
  `DELETE /api/contracts/{id}`.
- A finished job with some failed clauses is `done_with_warnings` with `error_code: "PARTIAL_EXTRACTION"`;
  those clauses have `extraction_state: "extraction_failed"`.
- **Errors** are `{error_code, message, action}` (see `app/errors.py`); failed jobs carry `error_code`,
  `error_message`, `error_action`.

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
| Dates, events API, completion cascade | | H7–9 |
| Rule edges, P2, recompute endpoints | | H9–12 |
