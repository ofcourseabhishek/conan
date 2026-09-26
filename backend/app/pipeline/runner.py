"""Job runner (TRD §10): in-process asyncio tasks, one jobs row per run, at most 2 at once.

Each stage persists its output idempotently (delete-then-insert for the contract), so a re-run
after a restart is safe. PDF bytes live only in memory until stage 1 has stored doc_text; a job
whose stage 1 already finished can be re-run without them.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
import uuid

from sqlalchemy import delete, func, update
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_engine
from app.errors import CATALOG, ConanError
from app.models import Clause, Contract, Job, Obligation, Page
from app.pipeline import dedupe, extract, ingest, segment
from app.pipeline.gemini import GeminiClient
from app.schemas import STAGES

log = logging.getLogger("conan.runner")

_sem: asyncio.Semaphore | None = None
_tasks: set[asyncio.Task] = set()  # hold references so tasks aren't garbage-collected mid-run
_pdf_bytes: dict[uuid.UUID, bytes] = {}  # job_id -> upload, dropped after stage 1
_client: GeminiClient | None = None


def llm_client() -> GeminiClient:
    """One client per process so the token bucket is shared by every job."""
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client


def set_llm_client(client: GeminiClient | None) -> None:  # tests
    global _client
    _client = client


def _semaphore() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(2)
    return _sem


def start_job(job_id: uuid.UUID, pdf: bytes | None = None) -> asyncio.Task:
    if pdf is not None:
        _pdf_bytes[job_id] = pdf
    task = asyncio.create_task(run_job(job_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


def _update_job(job_id: uuid.UUID, **fields) -> None:
    with Session(get_engine()) as s:
        job = s.get(Job, job_id)
        for k, v in fields.items():
            setattr(job, k, v)
        job.updated_at = dt.datetime.now(dt.timezone.utc)
        s.add(job)
        s.commit()


def _enter_stage(job_id: uuid.UUID, stage: str, message: str) -> None:
    i = STAGES.index(stage)
    _update_job(job_id, state="running", stage=stage, stage_index=i, stage_count=len(STAGES),
                progress_pct=int(100 * i / len(STAGES)), message=message)


async def run_job(job_id: uuid.UUID) -> None:
    async with _semaphore():
        t0 = time.monotonic()
        warnings: list[str] = []
        try:
            with Session(get_engine()) as s:
                job = s.get(Job, job_id)
                contract_id = job.contract_id
                n_clauses = s.exec(select(func.count()).select_from(Clause)
                                   .where(Clause.contract_id == contract_id)).one()

            if job_id in _pdf_bytes or n_clauses == 0:
                # Stage 1-2 are CPU-bound (PyMuPDF): run off the event loop.
                _enter_stage(job_id, "extract_pages", "Reading the PDF")
                doc = await asyncio.to_thread(_stage_ingest, job_id, contract_id)

                _enter_stage(job_id, "segment_clauses", "Finding clauses")
                n_clauses, fallback = await asyncio.to_thread(_stage_segment, contract_id, doc)
                if fallback:
                    warnings.append("No numbered headings found; clauses are paragraph windows.")
            # else: a requeued job whose clauses survived the restart resumes from stage 3

            _enter_stage(job_id, "extract_obligations", f"Reading {n_clauses} clauses with AI")
            client = llm_client()
            hits0, misses0 = client.hits, client.misses
            ex = await _stage_extract(contract_id, client)
            warnings += ex.warnings
            log.info("p1 job=%s cache_hits=%d cache_misses=%d", job_id, client.hits - hits0, client.misses - misses0)

            _enter_stage(job_id, "verify_dedupe", "Checking every quote against the PDF")
            n_obl, n_unverified = await asyncio.to_thread(_stage_verify, contract_id, ex)
            if n_obl == 0 and not ex.failed:
                raise ConanError("EMPTY_EXTRACTION")
            if n_unverified:
                warnings.append(f"{n_unverified} obligation(s) have evidence that could not be verified.")

            # Stages 5-7 (dates, edges, conflicts) land in H7-15.

            final = "done_with_warnings" if warnings else "done"
            _update_job(job_id, state=final, stage="done", stage_index=len(STAGES) - 1, progress_pct=100,
                        message=f"Found {n_obl} obligations in {n_clauses} clauses", warnings=warnings,
                        error_code="PARTIAL_EXTRACTION" if ex.failed else None)
            _set_contract_status(contract_id, "ready")
            log.info("job done job=%s ms=%d clauses=%d obligations=%d", job_id,
                     (time.monotonic() - t0) * 1000, n_clauses, n_obl)
        except ConanError as exc:
            log.warning("job failed job=%s code=%s", job_id, exc.code)
            _fail(job_id, exc.code, warnings)
        except Exception:
            log.exception("job crashed job=%s", job_id)
            _fail(job_id, "INTERNAL", warnings)
        finally:
            _pdf_bytes.pop(job_id, None)


def _fail(job_id: uuid.UUID, code: str, warnings: list[str]) -> None:
    try:
        _update_job(job_id, state="failed", error_code=code, message=CATALOG[code][1], warnings=warnings)
        with Session(get_engine()) as s:
            job = s.get(Job, job_id)
            _set_contract_status(job.contract_id, "failed")
    except Exception:
        log.exception("could not record failure job=%s", job_id)


def _set_contract_status(contract_id: uuid.UUID, status: str) -> None:
    with Session(get_engine()) as s:
        c = s.get(Contract, contract_id)
        c.status = status
        s.add(c)
        s.commit()


# ---------------------------------------------------------------- stages


def _stage_ingest(job_id: uuid.UUID, contract_id: uuid.UUID) -> ingest.IngestResult:
    st = get_settings()
    pdf = _pdf_bytes.get(job_id)
    if pdf is None:
        raise ConanError("INTERNAL", "PDF bytes unavailable (restart before ingest finished)")
    doc = ingest.extract(pdf, max_bytes=st.max_upload_bytes, max_pages=st.max_pages, timeout_s=st.parse_timeout_s)
    _pdf_bytes.pop(job_id, None)  # PDF bytes are discarded after ingest (TRD §5.1)
    with Session(get_engine()) as s:
        c = s.get(Contract, contract_id)
        c.doc_text, c.page_count = doc.doc_text, doc.page_count
        s.add(c)
        s.exec(delete(Page).where(Page.contract_id == contract_id))
        for i, (a, b) in enumerate(doc.page_offsets, start=1):
            s.add(Page(contract_id=contract_id, page_no=i, char_start=a, char_end=b))
        s.commit()
    return doc


def _stage_segment(contract_id: uuid.UUID, doc: ingest.IngestResult) -> tuple[int, bool]:
    seg = segment.segment(doc)
    with Session(get_engine()) as s:
        s.exec(delete(Clause).where(Clause.contract_id == contract_id))
        for c in seg.clauses:
            s.add(Clause(contract_id=contract_id, id=c.id, section_ref=c.section_ref, heading=c.heading,
                         category=segment.keyword_category(c.text), category_source="keyword",
                         char_start=c.char_start, char_end=c.char_end, page_start=c.page_start,
                         page_end=c.page_end, text=c.text, extraction_state="ok"))
        contract = s.get(Contract, contract_id)
        contract.parties = seg.parties
        s.add(contract)
        s.commit()
    return len(seg.clauses), seg.used_fallback


async def _stage_extract(contract_id: uuid.UUID, client: GeminiClient) -> extract.ExtractResult:
    with Session(get_engine()) as s:
        contract = s.get(Contract, contract_id)
        rows = s.exec(select(Clause).where(Clause.contract_id == contract_id).order_by(Clause.char_start)).all()
        clauses = [extract.ClauseIn(c.id, c.section_ref, c.text) for c in rows]
        parties, doc_text = list(contract.parties or []), contract.doc_text or ""
    glossary = segment.extract_glossary(doc_text)  # recomputed: deterministic, so restarts need no state
    ex = await extract.extract_all(client, clauses, parties, glossary, get_settings().batch_chars)
    with Session(get_engine()) as s:
        with_obl = {o.clause_id for o in ex.obligations}
        for c in s.exec(select(Clause).where(Clause.contract_id == contract_id)).all():
            if c.id in ex.categories:
                c.category, c.category_source = ex.categories[c.id], "llm"
            c.extraction_state = ("extraction_failed" if c.id in ex.failed
                                  else "ok" if c.id in with_obl else "no_obligations")
            s.add(c)
        s.commit()
    return ex


def _stage_verify(contract_id: uuid.UUID, ex: extract.ExtractResult) -> tuple[int, int]:
    with Session(get_engine()) as s:
        contract = s.get(Contract, contract_id)
        clauses = s.exec(select(Clause).where(Clause.contract_id == contract_id)).all()
        pages = s.exec(select(Page).where(Page.contract_id == contract_id).order_by(Page.page_no)).all()
        refs = [dedupe.ClauseRef(c.id, c.char_start, c.char_end, c.page_start) for c in clauses]
        cands = dedupe.verify_all(ex.obligations, refs, contract.doc_text or "",
                                  [(p.char_start, p.char_end) for p in pages], list(contract.parties or []))
        rows = dedupe.build_rows(contract_id, dedupe.dedupe(cands), {c.id: c.char_start for c in clauses})
        s.exec(delete(Obligation).where(Obligation.contract_id == contract_id))
        s.add_all(rows)
        # a reassigned quote can give a clause obligations after all
        with_obl = {r.clause_id for r in rows}
        for c in clauses:
            if c.extraction_state == "no_obligations" and c.id in with_obl:
                c.extraction_state = "ok"
                s.add(c)
        s.commit()
        return len(rows), sum(r.evidence_status != "verified" for r in rows)


# ---------------------------------------------------------------- startup recovery


def requeue_stale_jobs() -> list[uuid.UUID]:
    """Claim jobs stuck in running for > 2 minutes (TRD §10). After 3 attempts they fail."""
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=2)
    stmt = (update(Job)
            .where(Job.state.in_(("running", "queued")), Job.updated_at < cutoff)
            .values(attempts=Job.attempts + 1, state="queued")
            .returning(Job.id, Job.attempts))
    with Session(get_engine()) as s:
        rows = s.exec(stmt).all()
        s.commit()
    requeue = []
    for job_id, attempts in rows:
        if attempts > 3:
            _fail(job_id, "INTERNAL", ["Gave up after 3 restarts."])
        else:
            requeue.append(job_id)
    return requeue


def latest_job(session: Session, contract_id: uuid.UUID) -> Job | None:
    return session.exec(select(Job).where(Job.contract_id == contract_id).order_by(Job.updated_at.desc())).first()
