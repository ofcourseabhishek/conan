"""Write the real demo analysis to frontend/public/offline_fixture.json (the `?offline=1` fallback).

Goes through the real API in-process (FastAPI TestClient) against DATABASE_URL: clones the cached sample
(fixtures/demo_contract.pdf must already be seeded: scripts/seed_demo.py), sets a few dates a reviewer would
take straight from the contract or the demo story, reads the analysis for the demo's fixed "today", then
deletes the copy. No LLM call. The dates go in as user-set events, so the audit trail stays honest.

  cd backend
  .\\.venv\\Scripts\\python.exe scripts\\export_offline_fixture.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

AS_OF = "2026-10-28"  # the demo's fixed "today"
EVENTS = {
    "effective_date": "2026-09-01",  # preamble: "entered into as of 1 September 2026"
    "term_end": "2027-09-01",  # §2.1: ends 12 months after the Effective Date
    "po_issued": "2026-10-20",  # demo story: a purchase order went out on 20 Oct
}
OUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "offline_fixture.json"


def main() -> int:
    with TestClient(app) as c:
        r = c.post("/api/contracts/sample")
        body = r.json()
        if r.status_code != 200 or not body.get("cached"):
            print(f"Sample is not cached ({r.status_code} {body}); run scripts/seed_demo.py first.")
            if body.get("contract_id"):
                c.delete(f"/api/contracts/{body['contract_id']}")
            return 1
        cid = body["contract_id"]
        try:
            for key, date in EVENTS.items():
                r = c.put(f"/api/contracts/{cid}/events/{key}", params={"as_of": AS_OF}, json={"date": date})
                if r.status_code != 200:
                    print(f"Could not set {key}: {r.status_code} {r.text[:200]}")
                    return 1
            analysis = c.get(f"/api/contracts/{cid}/analysis", params={"as_of": AS_OF}).json()
        finally:
            c.delete(f"/api/contracts/{cid}")

    OUT.write_text(json.dumps(analysis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    s = analysis["stats"]
    dated = sum(o["due_date"] is not None for o in analysis["obligations"])
    print(f"wrote {OUT.relative_to(OUT.parents[2])}: {analysis['contract']['page_count']} pages, "
          f"{s['obligations']} obligations ({dated} dated), {len(analysis['edges'])} links, "
          f"{len(analysis['conflicts'])} conflict(s), as_of {analysis['as_of']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
