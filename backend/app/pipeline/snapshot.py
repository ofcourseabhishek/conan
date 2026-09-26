"""Analysis cache (TRD §10, plan §13 demo safety net).

A finished, fully-extracted job is snapshotted into analysis_cache keyed by (sha256, PIPELINE_VERSION).
A later upload of the same PDF, or "Try sample contract", clones the snapshot into a NEW contract in
well under a second, so no LLM is on the demo's critical path. Clones carry cached_at, which the UI
must show as "Cached analysis" (honest-fallback invariant). Each clone is independent: one viewer
marking something blocked never changes another viewer's copy.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlmodel import Session, select

from app.models import AnalysisCache, Clause, Conflict, Contract, Edge, Event, Job, Obligation, Page
from app.schemas import STAGES

_CHILDREN = {"pages": Page, "clauses": Clause, "obligations": Obligation, "edges": Edge, "events": Event,
             "conflicts": Conflict}


def _rows(s: Session, model, contract_id: uuid.UUID) -> list[dict]:
    rows = s.exec(select(model).where(model.contract_id == contract_id)).all()
    return [r.model_dump(mode="json", exclude={"contract_id"}) for r in rows]


def take(s: Session, contract_id: uuid.UUID) -> dict:
    c = s.get(Contract, contract_id)
    snap = {"contract": {"name": c.name, "filename": c.filename, "page_count": c.page_count,
                         "parties": c.parties, "doc_text": c.doc_text, "pipeline_version": c.pipeline_version}}
    for key, model in _CHILDREN.items():
        snap[key] = _rows(s, model, contract_id)
    # a snapshot is the pristine pipeline output: no reviewer dates, statuses or review states
    for e in snap["events"]:
        e["date"], e["date_source"] = None, None
    return snap


def save(s: Session, contract_id: uuid.UUID) -> None:
    c = s.get(Contract, contract_id)
    row = s.get(AnalysisCache, (c.sha256, c.pipeline_version))
    snap = take(s, contract_id)
    if row is None:
        s.add(AnalysisCache(sha256=c.sha256, pipeline_version=c.pipeline_version, snapshot=snap))
    else:
        row.snapshot, row.created_at = snap, dt.datetime.now(dt.timezone.utc)
        s.add(row)


def lookup(s: Session, sha256: str, pipeline_version: str) -> AnalysisCache | None:
    return s.get(AnalysisCache, (sha256, pipeline_version))


def clone(s: Session, cached: AnalysisCache, *, name: str | None = None, is_sample: bool = False) -> tuple[Contract, Job]:
    snap = cached.snapshot
    meta = snap["contract"]
    contract = Contract(name=name or meta["name"], filename=meta.get("filename"), sha256=cached.sha256,
                        page_count=meta["page_count"], parties=meta["parties"], doc_text=meta.get("doc_text"),
                        pipeline_version=cached.pipeline_version, is_sample=is_sample, status="ready",
                        cached_at=cached.created_at)
    s.add(contract)
    s.flush()
    cid = contract.id
    for key, model in _CHILDREN.items():
        for data in snap.get(key, []):
            data = {**data, "contract_id": cid}
            if key in ("edges", "conflicts"):
                data["id"] = uuid.uuid4()  # globally unique ids; obligation/clause ids are per contract
            if key == "obligations":
                data.update(review_state="proposed", status="open", completed_on=None)
            s.add(model.model_validate(data))
    job = Job(contract_id=cid, state="done", stage="done", stage_index=len(STAGES) - 1,
              stage_count=len(STAGES), progress_pct=100, message="Cached analysis")
    s.add(job)
    s.flush()
    return contract, job
