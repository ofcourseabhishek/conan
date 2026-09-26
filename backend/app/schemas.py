"""API contract (TRD §7). Single source of truth: exported to frontend/src/types/api.ts by
scripts/export_types.py. Change a model here, re-run the export, commit both.

LLM response schemas (P1/P2) live in app/pipeline/llm_schemas.py, not here.
"""

import datetime as dt
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Out(BaseModel):
    """Response models: fields with defaults are still always present in JSON, so mark them
    required in the exported JSON Schema / TS types."""
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

# ---------------------------------------------------------------- enums

EventKey = Literal[
    "effective_date", "po_issued", "delivery", "inspection_complete", "acceptance",
    "certificate_submitted", "invoice_receipt", "payment", "notice_given", "term_start",
    "term_end", "renewal", "termination", "other",
]
Category = Literal[
    "payment", "renewal", "termination", "compliance", "delivery", "penalty",
    "confidentiality", "other",
]
Modality = Literal["must", "must_not", "may"]
JobState = Literal["queued", "running", "done", "done_with_warnings", "failed"]
ExtractionState = Literal["ok", "extraction_failed", "no_obligations"]
EvidenceStatus = Literal["verified", "unverified"]
ReviewState = Literal["proposed", "confirmed", "edited", "rejected"]
ObligationStatus = Literal["open", "done", "blocked", "waived"]
ResolutionStatus = Literal[
    "resolved", "unresolved_trigger", "conditional_pending", "no_deadline", "ambiguous",
]
DateProvenance = Literal["contract_text", "user_event", "completion"]
EventDateSource = Literal["contract_text", "user", "completion"]
FieldProvenance = Literal["extracted", "computed", "ai_proposed", "user"]
Relation = Literal["must_precede", "condition_for", "depends_on", "may_trigger"]
EdgeSource = Literal["rule", "llm"]
EdgeStatus = Literal["proposed", "confirmed", "rejected", "auto_rejected"]
DeadlineKind = Literal["absolute", "relative", "recurring", "none"]
OffsetUnit = Literal["day", "week", "month", "year"]
DayType = Literal["calendar", "business", "unspecified"]
Direction = Literal["before", "after"]
RecurrenceFreq = Literal["weekly", "monthly", "quarterly", "annually"]
RiskBand = Literal["low", "medium", "high", "critical"]
RiskProvenance = Literal["computed", "extracted", "user"]
ConflictKind = Literal["offset_mismatch", "day_type_mismatch", "amount_mismatch", "date_mismatch", "notice_period", "llm"]
ErrorCode = Literal[
    "NOT_PDF", "TOO_LARGE", "TOO_MANY_PAGES", "ENCRYPTED", "NO_TEXT_LAYER", "LLM_QUOTA",
    "LLM_UNAVAILABLE", "PARTIAL_EXTRACTION", "EMPTY_EXTRACTION", "INTERNAL",
]

STAGES: list[str] = [
    "extract_pages", "segment_clauses", "extract_obligations", "verify_dedupe",
    "dates", "edges", "conflicts", "done",
]

DISCLAIMER = (
    "Conan is an operations aid, not legal advice. It flags potential inconsistencies but never "
    "decides which clause prevails. Risk scores are attention priority, not a probability of breach. "
    "Use only fictional or public contracts: free-tier AI inputs may be used by the provider."
)

# ---------------------------------------------------------------- nested values


class Party(Out):
    name: str
    role: str | None = None  # e.g. "Customer", "Supplier"


class Offset(Out):
    value: int
    unit: OffsetUnit
    day_type: DayType


class DeadlineRule(Out):
    kind: DeadlineKind
    raw_text: str | None = None
    absolute_date_text: str | None = None  # as written in the contract, e.g. "31 March 2027"
    absolute_date: dt.date | None = None  # only if the literal date string is in the verified quote
    offset: Offset | None = None
    direction: Direction | None = None
    anchor_event: EventKey | None = None
    recurrence: RecurrenceFreq | None = None
    is_conditional: bool = False


class Amount(Out):
    value: float
    currency: str | None = None


class PathStep(Out):
    edge_id: UUID
    upstream_id: str
    downstream_id: str
    relation: Relation
    quote: str | None = None
    page: int | None = None


class RiskFactor(Out):
    factor: str
    points: int
    provenance: RiskProvenance
    detail: str | None = None
    path: list[PathStep] | None = None  # only on the downstream-impact factor


class Risk(Out):
    score: int = Field(ge=0, le=100)
    band: RiskBand
    factors: list[RiskFactor]
    label: str = "Attention priority, not probability of breach"


# ---------------------------------------------------------------- rows


class ContractOut(Out):
    id: UUID
    name: str
    filename: str | None = None
    parties: list[Party]
    page_count: int
    is_sample: bool
    cached_at: dt.datetime | None = None  # set when this analysis came from analysis_cache
    pipeline_version: str
    created_at: dt.datetime


class ClauseOut(Out):
    id: str  # "C07"; server-assigned
    section_ref: str | None
    heading: str | None
    category: Category | None
    category_source: Literal["llm", "keyword"] | None = None
    char_start: int  # offsets into the document text; clause.text == doc_text[char_start:char_end]
    char_end: int
    page_start: int
    page_end: int
    text: str
    extraction_state: ExtractionState


class ObligationOut(Out):
    id: str  # "O-012"; server-assigned after dedupe
    clause_id: str
    actor: str
    counterparty: str | None
    modality: Modality
    action: str
    object: str | None
    category: Category
    trigger_event: EventKey | None
    trigger_label: str | None
    produces_event: EventKey | None
    is_conditional: bool
    condition_text: str | None
    deadline_rule: DeadlineRule
    amount: Amount | None
    penalty_text: str | None
    cross_refs: list[str]
    evidence_quote: str
    evidence_start: int | None  # absolute document offsets; None when unverified
    evidence_end: int | None
    evidence_status: EvidenceStatus
    evidence_score: int | None
    page_start: int
    page_end: int
    page_approx: bool  # true when unverified: page is the clause's first page
    llm_confidence: float | None
    confidence: float
    due_date: dt.date | None
    resolution_status: ResolutionStatus
    resolution_trace: str | None
    date_provenance: DateProvenance | None
    next_occurrences: list[dt.date] = []
    review_state: ReviewState
    needs_review: bool
    status: ObligationStatus
    completed_on: dt.date | None
    field_provenance: dict[str, FieldProvenance]
    risk: Risk


class EdgeOut(Out):
    id: UUID
    upstream_id: str
    downstream_id: str
    relation: Relation
    source: EdgeSource
    status: EdgeStatus
    rationale: str | None
    evidence_quote: str | None
    evidence_status: EvidenceStatus
    page: int | None
    confidence: float | None
    reject_reason: str | None
    propagates: bool  # eligible for D1 under the current reviewed_only setting


class EventOut(Out):
    key: str  # an EventKey, or "other:<slug>" for free-label events (never auto-merged)
    label: str
    date: dt.date | None
    date_source: EventDateSource | None
    source_obligation_id: str | None
    dependent_obligation_ids: list[str]  # obligations whose deadline waits on this event


class ConflictOut(Out):
    id: UUID
    kind: ConflictKind
    source: Literal["rule", "llm"]
    obligation_ids: list[str]
    clause_a: str
    clause_b: str
    description: str
    quote_a: str | None
    quote_b: str | None
    status: Literal["open", "dismissed"]


class ReviewActionOut(Out):
    id: int
    target_type: Literal["obligation", "edge", "event", "conflict"]
    target_id: str
    action: str
    before: dict | None
    after: dict | None
    note: str | None
    at: dt.datetime


class Stats(Out):
    clauses: int
    obligations: int
    unresolved_dates: int
    needs_review: int
    clauses_without_obligations: int
    warnings: list[str]


class Analysis(Out):
    contract: ContractOut
    as_of: dt.date
    reviewed_only: bool
    clauses: list[ClauseOut]
    obligations: list[ObligationOut]
    edges: list[EdgeOut]
    events: list[EventOut]
    conflicts: list[ConflictOut]
    review_actions: list[ReviewActionOut]
    stats: Stats
    disclaimer: str = DISCLAIMER


# ---------------------------------------------------------------- job + requests/responses


class JobOut(Out):
    id: UUID
    contract_id: UUID
    state: JobState
    stage: str
    stage_index: int
    stage_count: int
    progress_pct: int
    message: str | None
    warnings: list[str]
    error_code: ErrorCode | None
    error_message: str | None = None
    error_action: str | None = None


class UploadResponse(Out):
    contract_id: UUID
    job_id: UUID | None  # None when served from analysis_cache
    cached: bool


class ObligationPatch(BaseModel):
    """Editable fields. Anything set here gets field_provenance = "user"."""
    actor: str | None = None
    counterparty: str | None = None
    modality: Modality | None = None
    action: str | None = None
    object: str | None = None
    category: Category | None = None
    trigger_event: EventKey | None = None
    produces_event: EventKey | None = None
    deadline_rule: DeadlineRule | None = None
    penalty_text: str | None = None


class ObligationReviewRequest(BaseModel):
    action: Literal["confirm", "edit", "reject"]
    patch: ObligationPatch | None = None
    note: str | None = Field(default=None, max_length=500)


class ObligationStatusRequest(BaseModel):
    status: ObligationStatus
    occurred_on: dt.date | None = None  # with status=done: sets events[produces_event]


class EdgeReviewRequest(BaseModel):
    action: Literal["confirm", "reject"]
    note: str | None = Field(default=None, max_length=500)


class ConflictReviewRequest(BaseModel):
    action: Literal["dismiss", "reopen"]
    note: str | None = Field(default=None, max_length=500)


class EventDateRequest(BaseModel):
    date: dt.date | None


class RemindRequest(BaseModel):
    email: str = Field(max_length=254)


class ApiError(Out):
    error_code: ErrorCode
    message: str
    action: str


class Health(Out):
    ok: bool
    db: bool
    pipeline_version: str
    llm_mode: str
    llm_keys_total: int  # configured Gemini keys (never the keys themselves)
    llm_keys_available: int  # keys not parked for the day by a daily-quota 429
