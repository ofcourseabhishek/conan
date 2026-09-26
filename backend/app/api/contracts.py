import datetime as dt
import hashlib
import re
import time
import uuid
from collections import defaultdict, deque

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.api.assemble import build_analysis, get_contract_or_404, resolve_as_of
from app.config import get_settings
from app.db import get_session
from app.errors import ConanError
from app.models import Contract, Job
from app.pipeline import runner, snapshot
from app.pipeline.ingest import MAGIC
from app.schemas import Analysis, UploadResponse

router = APIRouter(prefix="/api")

UPLOADS_PER_HOUR = 10
_uploads: dict[str, deque] = defaultdict(deque)
CHUNK = 256 * 1024


def _allow_upload(ip: str) -> bool:
    q, now = _uploads[ip], time.monotonic()
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= UPLOADS_PER_HOUR:
        return False
    q.append(now)
    return True


def _display_name(filename: str | None) -> str:
    """Sanitized for display only; never used as a path."""
    stem = re.sub(r"\.pdf$", "", (filename or "contract").rsplit("/", 1)[-1].rsplit("\\", 1)[-1], flags=re.I)
    stem = re.sub(r"[^\w .,()&'-]+", " ", stem).strip()
    return (stem or "Contract")[:120]


SAMPLE_PDF = Path(__file__).resolve().parents[2] / "fixtures" / "demo_contract.pdf"
SAMPLE_NAME = "Sample: Master Supply & Services Agreement"


def _start_or_clone(s: Session, data: bytes, response: Response, *, name: str, filename: str,
                    is_sample: bool = False) -> UploadResponse:
    """Serve from analysis_cache when this exact PDF was analysed by this pipeline version (200),
    otherwise queue a job (202). Cached results are labelled via contract.cached_at."""
    st = get_settings()
    sha = hashlib.sha256(data).hexdigest()
    if cached := snapshot.lookup(s, sha, st.pipeline_version):
        contract, job = snapshot.clone(s, cached, name=name, is_sample=is_sample)
        s.commit()
        response.status_code = 200
        return UploadResponse(contract_id=contract.id, job_id=job.id, cached=True)
    contract = Contract(name=name, filename=filename, sha256=sha, pipeline_version=st.pipeline_version,
                        is_sample=is_sample)
    s.add(contract)
    s.flush()
    job = Job(contract_id=contract.id, message="Queued")
    s.add(job)
    s.commit()
    runner.start_job(job.id, data)
    return UploadResponse(contract_id=contract.id, job_id=job.id, cached=False)


@router.post("/contracts/sample", response_model=UploadResponse, status_code=202)
async def sample_contract(response: Response, s: Session = Depends(get_session)) -> UploadResponse:
    """'Try sample contract': a fresh copy of the bundled demo contract, from the cache when warm."""
    if not SAMPLE_PDF.exists():
        raise HTTPException(status_code=404, detail="Sample contract not bundled")
    return _start_or_clone(s, SAMPLE_PDF.read_bytes(), response, name=SAMPLE_NAME,
                           filename="demo_contract.pdf", is_sample=True)


@router.post("/contracts", response_model=UploadResponse, status_code=202)
async def upload_contract(request: Request, file: UploadFile, response: Response,
                          s: Session = Depends(get_session)):
    st = get_settings()
    ip = request.client.host if request.client else "unknown"
    if not _allow_upload(ip):
        return JSONResponse(status_code=429, content={
            "error_code": "INTERNAL", "message": "Too many uploads from this address.",
            "action": "Wait a while, or try the sample contract."})

    # Stream with a cap: never buffer more than max_upload_bytes + 1 chunk.
    buf, size = bytearray(), 0
    while chunk := await file.read(CHUNK):
        size += len(chunk)
        if size > st.max_upload_bytes:
            raise ConanError("TOO_LARGE")
        buf += chunk
        if len(buf) >= 1024 and MAGIC not in bytes(buf[:1024]):
            raise ConanError("NOT_PDF")
    data = bytes(buf)
    if MAGIC not in data[:1024]:
        raise ConanError("NOT_PDF")

    name = _display_name(file.filename)
    return _start_or_clone(s, data, response, name=name, filename=name + ".pdf")


@router.get("/contracts/{contract_id}/analysis", response_model=Analysis)
def get_analysis(contract_id: uuid.UUID, as_of: dt.date | None = None, reviewed_only: bool = False,
                 s: Session = Depends(get_session)) -> Analysis:
    contract = get_contract_or_404(s, contract_id)
    return build_analysis(s, contract, resolve_as_of(as_of), reviewed_only)


@router.delete("/contracts/{contract_id}", status_code=204)
def delete_contract(contract_id: uuid.UUID, s: Session = Depends(get_session)) -> Response:
    contract = get_contract_or_404(s, contract_id)
    s.delete(contract)  # every child table cascades ON DELETE
    s.commit()
    return Response(status_code=204)
