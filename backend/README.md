# Conan backend (Person A)

FastAPI + PyMuPDF + Gemini + Postgres. Spec: [docs/TRD.md](../docs/TRD.md). Plan: the council build plan.

## Run locally (Windows PowerShell 5.1: one command per line, no `&&`)

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env          # then edit .env; leave DATABASE_URL empty for local SQLite
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
.\.venv\Scripts\python.exe -m pytest -q
```

With `uv` installed, the first two setup lines can be `uv venv .venv --python 3.11` and
`uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt`. Git Bash / macOS / Linux: use
`.venv/Scripts/python` (Windows) or `.venv/bin/python`, and `cp` instead of `Copy-Item`.

Other scripts, all run from `backend\`:

```powershell
.\.venv\Scripts\python.exe scripts\gemini_smoke.py
.\.venv\Scripts\python.exe scripts\export_types.py
.\.venv\Scripts\python.exe scripts\make_fixture.py
.\.venv\Scripts\python.exe -m tests.eval_score --gold fixtures\gold.json --api http://localhost:8000 --contract <contract_id>
```

## For Person B (frontend)

- **Types:** `frontend/src/types/api.ts` is generated from `app/schemas.py`. Never edit it by hand; run
  `.\.venv\Scripts\python.exe scripts\export_types.py` after any schema change and commit both files.
- **Offline fixture:** `frontend/public/offline_fixture.json` is the real 8-page demo analysis (20 obligations,
  18 links, the §6.3 vs Sch. B conflict) with a few reviewer-set dates, read for `as_of` 2026-10-28. Regenerate it
  after re-seeding with `.\.venv\Scripts\python.exe scripts\export_offline_fixture.py`. Offsets and pages are real,
  so quote highlighting works: highlight
  `clause.text.slice(o.evidence_start - clause.char_start, o.evidence_end - clause.char_start)`.
  (`backend/fixtures/demo_analysis.json` is the small hand-written test fixture from `scripts/make_fixture.py`.)
- **Live today:** `GET /api/health`, `POST /api/contracts` (multipart `file`), `GET /api/jobs/{id}`,
  `GET /api/contracts/{id}/analysis?as_of=&reviewed_only=`, `DELETE /api/contracts/{id}`, and the mutations below.
  Every mutation accepts `?as_of=&reviewed_only=` and returns the full updated `Analysis` (replace your cache entry):
  - `PUT /api/contracts/{id}/events/{key}` `{date: "YYYY-MM-DD" | null}` — resolves every obligation waiting on it
  - `PATCH /api/obligations/{id}?contract_id=` `{action: confirm|edit|reject, patch?, note?}`
  - `PATCH /api/obligations/{id}/status?contract_id=` `{status, occurred_on?}` — `done` sets the event the
    obligation produces (completion cascade); moving back to `open` un-sets it. Use `blocked` for "Simulate blocked".
  - `PATCH /api/edges/{id}` `{action: confirm|reject}`
  - `PATCH /api/conflicts/{id}` `{action: dismiss|reopen}` (a dismissal survives later recomputes)
- `POST /api/contracts/sample` backs **Try sample contract**. `POST /api/contracts` and `/sample` return `200` with
  `cached: true` when the analysis comes from `analysis_cache` (the job is already `done`); otherwise `202`. When
  `contract.cached_at` is set, show a **Cached analysis** label. Every cached copy is independent.
- `GET /api/contracts/{id}/export.ics` (resolved deadlines, alarms 7 days and 1 day before) and `/export.csv`.
- Stretch: `POST /api/obligations/{id}/remind?contract_id=` `{email}` → `{sent, message}` sends one real test
  email (Resend). `503` when disabled, `422` for anything but one plain address, `429` over 3/hour per IP or the
  daily cap, `502` if Resend refuses (free tier: only the Resend account's own address). Show `detail` to the user.
  The SMS preview stays client-side, labelled **Simulated — not sent**.
- Edges: `source` is `rule` (deterministic) or `llm` (P2). Draw `proposed` dashed, `confirmed` solid; hide
  `rejected` / `auto_rejected` and, by default, `evidence_status: "unverified"`. `propagates` says whether the
  edge feeds downstream impact under the current `reviewed_only`.
- Events for `other` triggers are keyed `other:<obligation id>` and never merge.
- Recurring obligations (`deadline_rule.kind == "recurring"`) carry up to a year of `next_occurrences`;
  `due_date` in the analysis is the **next upcoming** occurrence for the requested `as_of` (risk uses the same).
  `recurrence_basis: "period_end"` schedules ("7 business days after each month end") start once the
  `effective_date` event has a date; until then they sit in the "Needs trigger date" lane like any other.
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

1. Put your key(s) in `backend/.env`, then `.\.venv\Scripts\python.exe scripts\gemini_smoke.py` confirms the model id and the
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
| Conflicts (D2): rule flags, notice periods, optional LLM layer, dismiss/reopen | `pipeline/conflicts.py` | done, tested |
| Analysis cache, `/sample`, seed script | `pipeline/snapshot.py`, `scripts/seed_demo.py` | done, tested; sample seeded in Neon |
| ICS / CSV export | `api/exports.py` | done, tested |
| Test email reminder (stretch) | `api/reminders.py` | done, tested; off until `ENABLE_REMINDERS=true` + `RESEND_API_KEY` |

`fixtures/demo_contract.pdf` is a synthetic placeholder until Person B's demo contract lands. After replacing it,
re-seed: `.\.venv\Scripts\python.exe scripts\seed_demo.py --force`. Do the same after any prompt change.
