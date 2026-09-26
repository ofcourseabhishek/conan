import datetime as dt
import hashlib
import re
import time
import uuid
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.api.assemble import build_analysis, get_contract_or_404, resolve_as_of
from app.config import get_settings
from app.db import get_session
from app.errors import ConanError
from app.models import Contract, Job
from app.pipeline import runner
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


@router.post("/contracts", response_model=UploadResponse, status_code=202)
async def upload_contract(request: Request, file: UploadFile, s: Session = Depends(get_session)):
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

    sha = hashlib.sha256(data).hexdigest()
    # (sha256, PIPELINE_VERSION) analysis_cache lookup lands with /sample at H13-15.

    contract = Contract(name=_display_name(file.filename), filename=_display_name(file.filename) + ".pdf",
                        sha256=sha, pipeline_version=st.pipeline_version)
    s.add(contract)
    s.flush()
    job = Job(contract_id=contract.id, message="Queued")
    s.add(job)
    s.commit()
    runner.start_job(job.id, data)
    return UploadResponse(contract_id=contract.id, job_id=job.id, cached=False)


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
