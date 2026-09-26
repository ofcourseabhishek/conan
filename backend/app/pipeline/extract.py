"""Stage 3: P1 obligation extraction (TRD §5.3, §8.3).

Whole clauses are packed into ~BATCH_CHARS batches. Per batch, the repair ladder is:
  1. response_schema (flat)            -> GeminiClient.generate
  2. item-level validation, keep valid items
  3. MAX_TOKENS finish -> split the batch once
  4. one re-ask with the validator error appended
  5. else mark the batch's clauses extraction_failed (job ends done_with_warnings)
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from app.errors import ConanError
from app.pipeline.gemini import GeminiClient, LLMResult
from app.pipeline.llm_schemas import FREE_TEXT_MAX, QUOTE_MAX, P1Clause, P1Obligation, P1Response

log = logging.getLogger("conan.extract")

P1_SYSTEM = (Path(__file__).resolve().parents[2] / "prompts" / "p1_system.txt").read_text(encoding="utf-8")
_FREE_TEXT = ("action", "object", "condition_text", "penalty_text", "trigger_label", "counterparty", "actor")
_TAG = re.compile(r"<\s*/?\s*clause", re.I)


@dataclass
class ClauseIn:
    id: str
    section_ref: str | None
    text: str


@dataclass
class ExtractResult:
    obligations: list[P1Obligation] = field(default_factory=list)
    categories: dict[str, str] = field(default_factory=dict)
    failed: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # ConanError codes from batches that failed outright

    def merge(self, other: "ExtractResult") -> None:
        self.obligations += other.obligations
        self.categories.update(other.categories)
        self.failed |= other.failed
        self.warnings += other.warnings
        self.errors += other.errors


def make_batches(clauses: list[ClauseIn], batch_chars: int) -> list[list[ClauseIn]]:
    batches, cur, size = [], [], 0
    for c in clauses:
        if cur and size + len(c.text) > batch_chars:
            batches.append(cur)
            cur, size = [], 0
        cur.append(c)
        size += len(c.text)
    if cur:
        batches.append(cur)
    return batches


def _escape(text: str) -> str:
    return _TAG.sub("[clause", text)  # contract text can't close or open our delimiter tags


def _attr(v: str | None) -> str:
    return (v or "").replace('"', "'")


def render_user(batch: list[ClauseIn], parties: list[dict], glossary: str) -> str:
    party_line = "; ".join(f"{p['name']} ({p['role']})" if p.get("role") else p["name"] for p in parties) or "(not detected)"
    body = "\n".join(f'<clause id="{c.id}" ref="{_attr(c.section_ref)}">{_escape(c.text)}</clause>' for c in batch)
    return f"PARTIES: {party_line}\nDEFINED TERMS:\n{glossary or '(none)'}\n\n{body}"


def validate(data: dict | None, ids: set[str]) -> tuple[list[P1Obligation], dict[str, str], list[str]]:
    """Item-level validation: keep every valid item, report the rest (no contract text in errors)."""
    if data is None:
        return [], {}, ["response was not valid JSON"]
    items, cats, errors = [], {}, []
    for i, raw in enumerate(data.get("clauses") or []):
        try:
            c = P1Clause.model_validate(raw)
            if c.clause_id in ids:
                cats[c.clause_id] = c.category
        except ValidationError as exc:
            errors.append(f"clauses[{i}]: {_short(exc)}")
    for i, raw in enumerate(data.get("obligations") or []):
        try:
            o = P1Obligation.model_validate(raw)
        except ValidationError as exc:
            errors.append(f"obligations[{i}]: {_short(exc)}")
            continue
        if o.clause_id not in ids:
            errors.append(f"obligations[{i}]: clause_id {o.clause_id!r} is not one of the given clauses")
            continue
        if len(o.evidence_quote) > QUOTE_MAX:
            errors.append(f"obligations[{i}]: evidence_quote longer than {QUOTE_MAX} characters")
            continue
        for f in _FREE_TEXT:
            v = getattr(o, f)
            if isinstance(v, str) and len(v) > FREE_TEXT_MAX:
                setattr(o, f, v[:FREE_TEXT_MAX])
        o.confidence = min(1.0, max(0.0, o.confidence))
        o.cross_refs = [r[:60] for r in o.cross_refs[:10]]
        items.append(o)
    return items, cats, errors


def _short(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:3])


async def run_batch(client: GeminiClient, batch: list[ClauseIn], parties: list[dict], glossary: str,
                    allow_split: bool = True) -> ExtractResult:
    ids = {c.id for c in batch}
    user = render_user(batch, parties, glossary)
    res = ExtractResult()
    try:
        r: LLMResult = await client.generate(P1_SYSTEM, user, P1Response)
        if r.truncated and len(batch) > 1 and allow_split:
            mid = len(batch) // 2
            halves = await asyncio.gather(*(run_batch(client, h, parties, glossary, allow_split=False)
                                            for h in (batch[:mid], batch[mid:])))
            for h in halves:
                res.merge(h)
            return res

        items, cats, errors = validate(r.data, ids)
        if r.truncated or (errors and not items):
            reason = "output was cut off (MAX_TOKENS); return fewer, shorter items" if r.truncated else "; ".join(errors[:5])
            retry = f"{user}\n\nYOUR PREVIOUS OUTPUT WAS INVALID: {reason}. Return valid JSON matching the schema."
            r2 = await client.generate(P1_SYSTEM, retry, P1Response)
            items2, cats2, errors2 = validate(r2.data, ids)
            if r2.data is not None and not r2.truncated and (items2 or not errors2):
                items, cats, errors = items2, cats2, errors2
            elif not items:
                res.failed |= ids
                res.warnings.append(f"{len(ids)} clause(s) could not be analyzed")
                return res
        if errors:
            log.info("p1 dropped %d invalid item(s) in batch of %d clauses", len(errors), len(batch))
        res.obligations, res.categories = items, cats
        return res
    except ConanError as exc:
        if exc.code not in ("LLM_QUOTA", "LLM_UNAVAILABLE"):
            raise
        res.failed |= ids
        res.errors.append(exc.code)
        res.warnings.append(f"{len(ids)} clause(s) could not be analyzed (AI service {exc.code})")
        return res


async def extract_all(client: GeminiClient, clauses: list[ClauseIn], parties: list[dict], glossary: str,
                      batch_chars: int) -> ExtractResult:
    batches = make_batches(clauses, batch_chars)
    results = await asyncio.gather(*(run_batch(client, b, parties, glossary) for b in batches))
    out = ExtractResult()
    for r in results:
        out.merge(r)
    if clauses and out.failed >= {c.id for c in clauses}:
        # Nothing analyzed at all: fail the job with the AI error rather than show an empty contract.
        raise ConanError(out.errors[0] if out.errors else "LLM_UNAVAILABLE")
    return out
