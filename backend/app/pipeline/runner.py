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
from app.models import Clause, Conflict, Contract, Edge, Job, Obligation, Page
from app.pipeline import conflicts, dedupe, edges, extract, ingest, segment, snapshot
from app.pipeline.gemini import GeminiClient
from app.pipeline.recompute import recompute
from app.schemas import STAGES

log = logging.getLogger("conan.runner")

_sem: asyncio.Semaphore | None = None
_tasks: set[asyncio.Task] = set()  # hold references so tasks aren't garbage-collected mid-run
_pdf_bytes: dict[uuid.UUID, bytes] = {}  # job_id -> upload, dropped after stage 1
_owned: set[uuid.UUID] = set()  # jobs this process is running or queueing: never reclaimed by our own sweep
_client: GeminiClient | None = None

HEARTBEAT_S = 30  # a live job touches updated_at this often, so it never looks stale to another instance
STALE_AFTER = dt.timedelta(minutes=2)
SWEEP_S = 60
SAMPLE_TTL = dt.timedelta(hours=24)


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
    _owned.add(job_id)
    task = asyncio.create_task(_run_with_heartbeat(job_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


async def _run_with_heartbeat(job_id: uuid.UUID) -> None:
    beat = asyncio.create_task(_heartbeat(job_id))
    try:
        await run_job(job_id)
    finally:
        beat.cancel()
        _owned.discard(job_id)


async def _heartbeat(job_id: uuid.UUID) -> None:
    """Keeps updated_at fresh while queued or running (one P1 call alone can exceed STALE_AFTER when
    Gemini is overloaded), so a second instance during a deploy never re-runs a live job."""
    while True:
        await asyncio.sleep(HEARTBEAT_S)
        try:
            await asyncio.to_thread(_touch, job_id)
        except Exception:  # a missed beat only risks a (memoized, cheap) re-run
            log.warning("heartbeat failed job=%s", job_id)


def _touch(job_id: uuid.UUID) -> None:
    with Session(get_engine()) as s:
        s.exec(update(Job).where(Job.id == job_id, Job.state.in_(("queued", "running")))
               .values(updated_at=dt.datetime.now(dt.timezone.utc)))
        s.commit()


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

            _enter_stage(job_id, "dates", "Working out deadlines")
            await asyncio.to_thread(_stage_dates, contract_id)

            _enter_stage(job_id, "edges", "Linking obligations")
            edge_warnings, llm_conflicts = await _stage_edges(contract_id, client)
            warnings += edge_warnings

            _enter_stage(job_id, "conflicts", "Looking for inconsistent terms")
            await asyncio.to_thread(_stage_conflicts, contract_id, llm_conflicts)

            if not ex.failed:  # cache first, so the result is cacheable the moment the job reads done;
                await asyncio.to_thread(_save_snapshot, contract_id)  # never cache a partial result
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


async def _stage_edges(contract_id: uuid.UUID, client: GeminiClient) -> tuple[list[str], list]:
    with Session(get_engine()) as s:
        contract = s.get(Contract, contract_id)
        obligations = s.exec(select(Obligation).where(Obligation.contract_id == contract_id)).all()
        clauses = s.exec(select(Clause).where(Clause.contract_id == contract_id)).all()
        pages = s.exec(select(Page).where(Page.contract_id == contract_id).order_by(Page.page_no)).all()
        doc_text = contract.doc_text or ""
        s.expunge_all()  # plain objects from here on; the LLM call must not hold a session open
    res = await edges.build_edges(contract_id, obligations, clauses, doc_text,
                                  [(p.char_start, p.char_end) for p in pages], client,
                                  enable_llm=get_settings().enable_p2_llm)
    with Session(get_engine()) as s:
        s.exec(delete(Edge).where(Edge.contract_id == contract_id))
        s.add_all(res.edges)
        s.commit()
    return res.warnings, res.llm_conflicts


def _stage_conflicts(contract_id: uuid.UUID, llm_proposals) -> None:
    with Session(get_engine()) as s:
        s.exec(delete(Conflict).where(Conflict.contract_id == contract_id))
        recompute(s, contract_id)  # dates + rule conflicts
        if get_settings().enable_llm_conflicts and llm_proposals:
            contract = s.get(Contract, contract_id)
            obligations = s.exec(select(Obligation).where(Obligation.contract_id == contract_id)).all()
            pages = s.exec(select(Page).where(Page.contract_id == contract_id).order_by(Page.page_no)).all()
            s.add_all(conflicts.llm_conflicts(contract_id, llm_proposals, obligations, contract.doc_text or "",
                                              [(p.char_start, p.char_end) for p in pages]))
        s.commit()


def _save_snapshot(contract_id: uuid.UUID) -> None:
    try:
        with Session(get_engine()) as s:
            snapshot.save(s, contract_id)
            s.commit()
    except Exception:  # the cache is an optimisation; never fail a finished job over it
        log.exception("snapshot failed contract=%s", contract_id)


def _stage_dates(contract_id: uuid.UUID) -> None:
    with Session(get_engine()) as s:
        recompute(s, contract_id)
        s.commit()


# ---------------------------------------------------------------- startup recovery


def requeue_stale_jobs() -> list[uuid.UUID]:
    """Claim jobs whose heartbeat stopped > 2 minutes ago (TRD §10): their process died. The atomic
    UPDATE ... RETURNING means only one instance claims each job. After 3 attempts they fail."""
    cutoff = dt.datetime.now(dt.timezone.utc) - STALE_AFTER
    stmt = (update(Job)
            .where(Job.state.in_(("running", "queued")), Job.updated_at < cutoff)
            .values(attempts=Job.attempts + 1, state="queued")
            .returning(Job.id, Job.attempts))
    if _owned:
        stmt = stmt.where(Job.id.not_in(list(_owned)))
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


def delete_old_samples() -> int:
    """'Try sample' makes a fresh copy per click; drop copies older than a day so they can't pile up."""
    cutoff = dt.datetime.now(dt.timezone.utc) - SAMPLE_TTL
    with Session(get_engine()) as s:
        n = s.exec(delete(Contract).where(Contract.is_sample, Contract.created_at < cutoff)).rowcount
        s.commit()
    return n or 0


async def sweeper() -> None:
    """Background loop: restart-recovery on boot and every minute after, plus sample cleanup."""
    while True:
        try:
            for job_id in await asyncio.to_thread(requeue_stale_jobs):
                log.info("requeued stale job=%s", job_id)
                start_job(job_id)
            if n := await asyncio.to_thread(delete_old_samples):
                log.info("deleted %d old sample copies", n)
        except Exception:
            log.exception("sweep failed")
        await asyncio.sleep(SWEEP_S)


def latest_job(session: Session, contract_id: uuid.UUID) -> Job | None:
    return session.exec(select(Job).where(Job.contract_id == contract_id).order_by(Job.updated_at.desc())).first()
