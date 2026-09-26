"""SQLModel tables mirroring the reference DDL in TRD §6.

JSON columns use JSONB on Postgres and plain JSON elsewhere, so tests can run on SQLite.
No migrations: a schema change during the hackathon means drop + scripts/seed_demo.py.
"""

import uuid
import datetime as dt

from sqlalchemy import JSON, Column, ForeignKey, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

JSONType = JSON().with_variant(JSONB(), "postgresql")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _json(default=None, nullable=True):
    return Field(default_factory=(lambda: default() if callable(default) else default),
                 sa_column=Column(JSONType, nullable=nullable))


def _contract_fk(primary_key: bool = False):
    return Field(sa_column=Column(Uuid, ForeignKey("contracts.id", ondelete="CASCADE"),
                                  primary_key=primary_key, nullable=False, index=not primary_key))


class Contract(SQLModel, table=True):
    __tablename__ = "contracts"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    filename: str | None = None
    sha256: str = Field(index=True)
    page_count: int = 0
    parties: list = _json(list)
    status: str = "processing"
    pipeline_version: str
    is_sample: bool = False
    cached_at: dt.datetime | None = None
    doc_text: str | None = None  # extracted text (PDF bytes are discarded); all offsets index into this
    created_at: dt.datetime = Field(default_factory=_now)


class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    contract_id: uuid.UUID = _contract_fk()
    state: str = "queued"
    stage: str = "extract_pages"
    stage_index: int = 0
    stage_count: int = 8
    progress_pct: int = 0
    message: str | None = None
    warnings: list = _json(list)
    error_code: str | None = None
    attempts: int = 0
    updated_at: dt.datetime = Field(default_factory=_now, index=True)


class Page(SQLModel, table=True):
    __tablename__ = "pages"
    contract_id: uuid.UUID = _contract_fk(primary_key=True)
    page_no: int = Field(primary_key=True)
    char_start: int
    char_end: int


class Clause(SQLModel, table=True):
    __tablename__ = "clauses"
    contract_id: uuid.UUID = _contract_fk(primary_key=True)
    id: str = Field(primary_key=True)
    section_ref: str | None = None
    heading: str | None = None
    category: str | None = None
    category_source: str | None = None
    char_start: int
    char_end: int
    page_start: int
    page_end: int
    text: str
    extraction_state: str = "ok"


class Obligation(SQLModel, table=True):
    __tablename__ = "obligations"
    contract_id: uuid.UUID = _contract_fk(primary_key=True)
    id: str = Field(primary_key=True)
    clause_id: str
    actor: str
    counterparty: str | None = None
    modality: str = "must"
    action: str
    object: str | None = None
    category: str = "other"
    trigger_event: str | None = None
    trigger_label: str | None = None
    produces_event: str | None = None
    is_conditional: bool = False
    condition_text: str | None = None
    deadline_rule: dict = _json(lambda: {"kind": "none"})
    amount: dict | None = _json(None)
    penalty_text: str | None = None
    cross_refs: list = _json(list)
    evidence_quote: str
    evidence_start: int | None = None
    evidence_end: int | None = None
    evidence_status: str = "unverified"
    evidence_score: int | None = None
    page_start: int
    page_end: int
    page_approx: bool = False
    llm_confidence: float | None = None
    confidence: float = 0.0
    due_date: dt.date | None = None
    resolution_status: str = "no_deadline"
    resolution_trace: str | None = None
    date_provenance: str | None = None
    next_occurrences: list = _json(list)
    review_state: str = "proposed"
    status: str = "open"
    completed_on: dt.date | None = None
    field_provenance: dict = _json(dict)


class Edge(SQLModel, table=True):
    __tablename__ = "edges"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    contract_id: uuid.UUID = _contract_fk()
    upstream_id: str
    downstream_id: str
    relation: str
    source: str
    status: str = "proposed"
    rationale: str | None = None
    evidence_quote: str | None = None
    evidence_status: str = "unverified"
    page: int | None = None
    confidence: float | None = None
    reject_reason: str | None = None


class Event(SQLModel, table=True):
    __tablename__ = "events"
    contract_id: uuid.UUID = _contract_fk(primary_key=True)
    key: str = Field(primary_key=True)
    label: str
    date: dt.date | None = None
    date_source: str | None = None
    source_obligation_id: str | None = None


class Conflict(SQLModel, table=True):
    __tablename__ = "conflicts"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    contract_id: uuid.UUID = _contract_fk()
    kind: str
    source: str = "rule"
    obligation_ids: list = _json(list)
    clause_a: str
    clause_b: str
    description: str
    quote_a: str | None = None
    quote_b: str | None = None
    status: str = "open"


class ReviewAction(SQLModel, table=True):
    __tablename__ = "review_actions"
    id: int | None = Field(default=None, primary_key=True)
    contract_id: uuid.UUID = _contract_fk()
    target_type: str
    target_id: str
    action: str
    before: dict | None = _json(None)
    after: dict | None = _json(None)
    note: str | None = None
    at: dt.datetime = Field(default_factory=_now)


class LLMCache(SQLModel, table=True):
    __tablename__ = "llm_cache"
    key: str = Field(primary_key=True)  # sha256(model|prompt_version|schema_hash|input)
    response: dict = _json(dict, nullable=False)
    created_at: dt.datetime = Field(default_factory=_now)


class AnalysisCache(SQLModel, table=True):
    __tablename__ = "analysis_cache"
    sha256: str = Field(primary_key=True)
    pipeline_version: str = Field(primary_key=True)
    snapshot: dict = _json(dict, nullable=False)
    created_at: dt.datetime = Field(default_factory=_now)
