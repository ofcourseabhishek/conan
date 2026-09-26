import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.errors import CATALOG
from app.models import Job
from app.schemas import JobOut

router = APIRouter(prefix="/api")


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, s: Session = Depends(get_session)) -> JobOut:
    job = s.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    out = JobOut.model_validate(job, from_attributes=True)
    if job.error_code:
        _, out.error_message, out.error_action = CATALOG[job.error_code]
    return out
