"""Gemini response schemas (TRD §8.3, §8.4). Deliberately FLAT: nullable scalars and enums only,
no unions or deep nesting, because large nested schemas are a known cause of structured-output
400/500s. The LLM never outputs IDs (other than echoing clause/obligation IDs we gave it) or pages.

Length caps are enforced by item-level validation in extract.py, not in the schema sent to Gemini.
"""

from pydantic import BaseModel

from app.schemas import (
    Category, DayType, DeadlineKind, Direction, EventKey, Modality, OffsetUnit, RecurrenceBasis, RecurrenceFreq,
    Relation,
)

QUOTE_MAX, FREE_TEXT_MAX = 400, 300


class P1Clause(BaseModel):
    clause_id: str
    category: Category


class P1Obligation(BaseModel):
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
    deadline_kind: DeadlineKind
    absolute_date_text: str | None
    offset_value: int | None
    offset_unit: OffsetUnit | None
    day_type: DayType | None
    direction: Direction | None
    recurrence_freq: RecurrenceFreq | None
    recurrence_basis: RecurrenceBasis | None = None
    amount_value: float | None
    amount_currency: str | None
    penalty_text: str | None
    cross_refs: list[str]
    evidence_quote: str
    confidence: float


class P1Response(BaseModel):
    clauses: list[P1Clause]
    obligations: list[P1Obligation]


class P2Edge(BaseModel):
    upstream_id: str
    downstream_id: str
    relation: Relation
    evidence_quote: str
    clause_id: str | None
    rationale: str | None
    confidence: float


class P2Conflict(BaseModel):
    obligation_a: str
    obligation_b: str
    quote_a: str
    quote_b: str
    description: str


class P2Response(BaseModel):
    edges: list[P2Edge]
    potential_conflicts: list[P2Conflict]
