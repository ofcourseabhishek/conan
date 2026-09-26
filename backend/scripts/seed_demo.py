"""Pre-run the bundled sample contract (fixtures/demo_contract.pdf) through the real pipeline and store
it in analysis_cache, so "Try sample contract" is served in about a second with no LLM call.

Uses DATABASE_URL and the Gemini keys from backend/.env. Local and Render share the Neon database,
so seeding from a laptop warms the deployed server too (same PIPELINE_VERSION required).

  cd backend
  .\\.venv\\Scripts\\python.exe scripts\\seed_demo.py            # no-op if already cached
  .\\.venv\\Scripts\\python.exe scripts\\seed_demo.py --force    # re-run (after a prompt or PDF change)
"""

import argparse
import asyncio
import hashlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session  # noqa: E402

from app.api.contracts import SAMPLE_NAME, SAMPLE_PDF  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import get_engine, init_db  # noqa: E402
from app.models import Contract, Job  # noqa: E402
from app.pipeline import runner, snapshot  # noqa: E402


async def main(force: bool) -> int:
    st = get_settings()
    init_db()
    data = SAMPLE_PDF.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    with Session(get_engine()) as s:
        row = snapshot.lookup(s, sha)
        if row and not force:
            print(f"Already cached ({row.pipeline_version}, {row.created_at:%Y-%m-%d %H:%M} UTC). Use --force to re-run.")
            return 0
        if row:
            s.delete(row)
        contract = Contract(name=SAMPLE_NAME, filename="demo_contract.pdf", sha256=sha,
                            pipeline_version=st.pipeline_version, is_sample=True)
        s.add(contract)
        s.flush()
        job = Job(contract_id=contract.id, message="Queued (seed)")
        s.add(job)
        s.commit()
        job_id, contract_id = job.id, contract.id

    print(f"Running the pipeline on {SAMPLE_PDF.name} with {st.models[0]} (fallbacks: {', '.join(st.models[1:])})...")
    t0 = time.monotonic()
    await runner.start_job(job_id, data)
    with Session(get_engine()) as s:
        job = s.get(Job, job_id)
        cached = snapshot.lookup(s, sha) is not None
    print(f"{job.state} in {time.monotonic() - t0:.0f}s: {job.message}")
    for w in job.warnings:
        print("  warning:", w)
    if job.error_code:
        print("  error_code:", job.error_code)
    print(f"contract_id={contract_id}  cached={'yes' if cached else 'NO (partial or failed result is never cached)'}")
    return 0 if cached else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    sys.exit(asyncio.run(main(ap.parse_args().force)))
