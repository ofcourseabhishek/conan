import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import contracts, exports, jobs, reminders, review
from app.config import get_settings
from app.db import init_db, ping
from app.errors import ConanError, conan_error_handler
from app.pipeline import runner
from app.schemas import Health

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
# Never log prompts, responses or contract text (TRD §12): keep SDK/http debug logging off.
for noisy in ("google_genai", "google.genai", "httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    for job_id in runner.requeue_stale_jobs():  # restart recovery; memoized LLM calls make re-runs cheap
        runner.start_job(job_id)
    yield


settings = get_settings()
app = FastAPI(title="Conan API", version=settings.pipeline_version, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["*"],
)
app.add_exception_handler(ConanError, conan_error_handler)
app.include_router(contracts.router)
app.include_router(jobs.router)
app.include_router(review.router)
app.include_router(exports.router)
app.include_router(reminders.router)


@app.get("/api/health", response_model=Health)
def health() -> Health:
    pool = runner.llm_client().pool
    total = len(settings.api_keys)
    return Health(ok=True, db=ping(), pipeline_version=settings.pipeline_version, llm_mode=settings.llm_mode,
                  llm_keys_total=total, llm_keys_available=pool.available() if total else 0)
