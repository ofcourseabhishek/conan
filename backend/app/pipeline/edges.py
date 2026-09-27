"""Stage 6: dependency edges (TRD §9.3).

Rule edges first (free, deterministic, evidence verbatim by construction), then optional P2 LLM
proposals, validated in order: IDs -> quote verified in an allowed clause -> dedupe (rule wins) ->
cycle breaking (lowest-confidence LLM edge auto_rejected; rule edges never removed).
Every edge starts `proposed`; a person confirms or rejects it.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from app.errors import ConanError
from app.models import Edge
from app.pipeline.gemini import GeminiClient
from app.pipeline.llm_schemas import P2Conflict, P2Edge, P2Response
from app.pipeline.temporal import is_per_obligation
from app.pipeline.verify import _search, normalize, page_of

log = logging.getLogger("conan.edges")

P2_SYSTEM = (Path(__file__).resolve().parents[2] / "prompts" / "p2_system.txt").read_text(encoding="utf-8")
ACYCLIC = {"must_precede", "condition_for", "depends_on"}  # may_trigger cycles are allowed
MAX_P2_OBLIGATIONS, MAX_SNIPPET_CHARS, MAX_FANOUT = 80, 6000, 4

_REF = r"(?:Section|Clause|Article|Schedule|Annex(?:ure)?|Exhibit|Appendix)\s+(?P<ref>\d+(?:\.\d+)*|[A-Z]\b)"
_CROSS = re.compile(r"\b(?:subject to|in accordance with|as set forth in|as set out in|pursuant to|under)\s+"
                    + _REF, re.I)
_FAIL = re.compile(r"\b(?:fail(?:s|ure)?|breach(?:es)?|default|delay(?:s)?|does not|non-?compliance)\b[^.;]{0,120}?"
                   + _REF, re.I)
_TRIGGERISH = re.compile(r"\b(section|clause|schedule|subject to|upon|following|prior to|after|before|"
                         r"condition|provided that|in the event)\b", re.I)


@dataclass
class EdgeResult:
    edges: list[Edge]
    warnings: list[str] = field(default_factory=list)
    llm_conflicts: list[P2Conflict] = field(default_factory=list)


def _active(obligations):
    return [o for o in obligations if o.review_state != "rejected"]


def _ref_key(ref: str) -> str:
    return ref.strip().rstrip(".").casefold()


def _clauses_for_ref(ref: str, clauses) -> list:
    """'5' matches clause 5 and 5.x; '5.1' matches 5.1 and 5.1(a); 'B' matches 'Sch. B'."""
    k = _ref_key(ref)
    out = []
    for c in clauses:
        sr = _ref_key(c.section_ref or "")
        if sr == k or sr.startswith(k + ".") or sr.startswith(k + "(") or sr.split(" ")[-1] == k:
            out.append(c)
    return out


def _sentence_window(text: str, start: int, end: int, limit: int = 240) -> tuple[int, int]:
    s = max(text.rfind(".", 0, start), text.rfind(";", 0, start), text.rfind("\n\n", 0, start)) + 1
    e_candidates = [i for i in (text.find(".", end), text.find(";", end)) if i != -1]
    e = min(e_candidates) + 1 if e_candidates else len(text)
    s = max(s, start - limit // 2)
    e = min(e, end + limit // 2)
    while s < e and text[s].isspace():
        s += 1
    return s, e


def _rule_edge(contract_id, up, down, relation, quote, page, rationale, verified=True) -> Edge:
    return Edge(contract_id=contract_id, upstream_id=up, downstream_id=down, relation=relation, source="rule",
                rationale=rationale, evidence_quote=quote, evidence_status="verified" if verified else "unverified",
                page=page)


def rule_edges(contract_id: uuid.UUID, obligations, clauses, page_offsets) -> list[Edge]:
    obls = _active(obligations)
    by_clause = defaultdict(list)
    for o in obls:
        by_clause[o.clause_id].append(o)
    edges: list[Edge] = []

    # event chain: A produces X, B is triggered by X
    producers = defaultdict(list)
    for o in obls:
        if o.produces_event and not is_per_obligation(o.produces_event):
            producers[o.produces_event].append(o)
    for b in obls:
        trig = (b.deadline_rule or {}).get("anchor_event") or b.trigger_event
        if not trig or is_per_obligation(trig):
            continue
        for a in producers.get(trig, []):
            if a.id == b.id:
                continue
            quote = (b.deadline_rule or {}).get("raw_text") or b.evidence_quote
            edges.append(_rule_edge(contract_id, a.id, b.id, "must_precede", quote, b.page_start,
                                    f"{a.id} produces '{trig}', which starts {b.id}'s deadline.",
                                    b.evidence_status == "verified"))

    # cross-reference and penalty rules, read from the clause text itself
    for c in clauses:
        downs = by_clause.get(c.id, [])
        if not downs:
            continue
        fail_spans = [m.span() for m in _FAIL.finditer(c.text)]
        for pattern, relation in ((_CROSS, "depends_on"), (_FAIL, "may_trigger")):
            for m in pattern.finditer(c.text):
                if relation == "depends_on" and any(a <= m.start() < b for a, b in fail_spans):
                    continue  # "fails to deliver under Section 3.1" is a penalty link, not a dependency
                targets = [t for t in _clauses_for_ref(m.group("ref"), clauses) if t.id != c.id]
                ups = [o for t in targets for o in by_clause.get(t.id, [])]
                if not ups or len(ups) > MAX_FANOUT:
                    continue
                ws, we = _sentence_window(c.text, m.start(), m.end())
                quote = c.text[ws:we].strip()
                page = page_of(page_offsets, c.char_start + ws)
                recipients = downs
                if relation == "may_trigger":
                    recipients = [o for o in downs if o.category in ("penalty", "termination") or o.penalty_text]
                for u in ups:
                    for d in recipients:
                        if u.id == d.id:
                            continue
                        why = (f"§{c.section_ref} refers to the failure of §{targets[0].section_ref}."
                               if relation == "may_trigger" else f"§{c.section_ref} is subject to §{targets[0].section_ref}.")
                        edges.append(_rule_edge(contract_id, u.id, d.id, relation, quote, page, why))
    return _dedupe(edges)


def _dedupe(edges: list[Edge]) -> list[Edge]:
    """On (upstream, downstream, relation) collisions the rule edge wins; LLM rationale is appended."""
    out: dict[tuple, Edge] = {}
    for e in edges:
        k = (e.upstream_id, e.downstream_id, e.relation)
        cur = out.get(k)
        if cur is None:
            out[k] = e
        elif cur.source == "rule" and e.source == "llm":
            if e.rationale and e.rationale not in (cur.rationale or ""):
                cur.rationale = f"{cur.rationale} AI note: {e.rationale}"
        elif cur.source == "llm" and e.source == "rule":
            if cur.rationale:
                e.rationale = f"{e.rationale} AI note: {cur.rationale}"
            out[k] = e
        elif (e.confidence or 0) > (cur.confidence or 0):
            out[k] = e
    return list(out.values())


# ---------------------------------------------------------------- P2


def _line(o, section: dict[str, str]) -> str:
    r = o.deadline_rule or {}
    off = r.get("offset") or {}
    trig = o.trigger_event or "-"
    if off:
        sign = "-" if r.get("direction") == "before" else "+"
        trig += f" {sign}{off.get('value')} {off.get('day_type', '')} {off.get('unit')}s".replace("  ", " ")
    return (f"{o.id} | {o.actor} | {o.action} | {(o.object or '')[:50]} | trigger: {trig} | "
            f"§{section.get(o.clause_id, '?')} | produces: {o.produces_event or '-'}")


def render_p2(obls, clauses) -> str:
    section = {c.id: c.section_ref or c.id for c in clauses}
    used = {o.clause_id for o in obls}
    snippets, size = [], 0
    for c in clauses:
        if c.id not in used:
            continue
        for sent in re.split(r"(?<=[.;])\s+", " ".join(c.text.split())):
            if _TRIGGERISH.search(sent) and 20 <= len(sent) <= 400:
                item = f'<snippet clause="{c.id}" ref="{section[c.id]}">{sent.replace("<", "[")}</snippet>'
                if size + len(item) > MAX_SNIPPET_CHARS:
                    break
                snippets.append(item)
                size += len(item)
    lines = "\n".join(_line(o, section) for o in obls)
    return f"OBLIGATIONS (one per line):\n{lines}\n\nSNIPPETS:\n" + "\n".join(snippets)


def _verify_in(quote: str, doc_text: str, spans: list[tuple[int, int]]) -> tuple[bool, int | None]:
    q = normalize(quote).text.strip(" \"'")
    if len(q) < 20:
        return False, None
    threshold = 95.0 if len(q) < 40 else 92.0
    for s, e in spans:
        m = _search(doc_text[s:e], s, q, threshold)
        if m and m.status == "verified":
            return True, m.start
    return False, None


def validate_llm_edges(contract_id: uuid.UUID, proposals, obligations, clauses, doc_text: str,
                       page_offsets) -> tuple[list[Edge], list[str]]:
    obls = {o.id: o for o in _active(obligations)}
    by_id = {c.id: c for c in clauses}
    dropped = 0
    out = []
    for p in proposals:
        if p.upstream_id not in obls or p.downstream_id not in obls or p.upstream_id == p.downstream_id:
            dropped += 1
            continue
        up, down = obls[p.upstream_id], obls[p.downstream_id]
        allowed = {up.clause_id, down.clause_id}
        for o in (up, down):
            for ref in o.cross_refs or []:
                m = re.search(r"(\d+(?:\.\d+)*|\b[A-Z]\b)\s*$", ref.strip())
                if m:
                    allowed |= {c.id for c in _clauses_for_ref(m.group(1), clauses)}
        spans = [(by_id[c].char_start, by_id[c].char_end) for c in allowed if c in by_id]
        ok, at = _verify_in(p.evidence_quote, doc_text, spans)
        out.append(Edge(contract_id=contract_id, upstream_id=p.upstream_id, downstream_id=p.downstream_id,
                        relation=p.relation, source="llm", rationale=(p.rationale or "")[:300] or None,
                        evidence_quote=p.evidence_quote[:400], evidence_status="verified" if ok else "unverified",
                        page=page_of(page_offsets, at) if ok else None, confidence=min(1.0, max(0.0, p.confidence))))
    warnings = [f"{dropped} AI link proposal(s) referenced unknown obligations and were dropped."] if dropped else []
    return out, warnings


async def propose_llm_edges(client: GeminiClient, obligations, clauses) -> tuple[list, list[P2Conflict]]:
    """One P2 call per <=80 obligations (doc order). Cross-chunk links are left to the rules."""
    obls = sorted(_active(obligations), key=lambda o: o.id)
    edges, conflicts = [], []
    for i in range(0, len(obls), MAX_P2_OBLIGATIONS):
        chunk = obls[i:i + MAX_P2_OBLIGATIONS]
        r = await client.generate(P2_SYSTEM, render_p2(chunk, clauses), P2Response)
        if r.data is None:
            raise ConanError("LLM_UNAVAILABLE", "P2 returned no JSON")
        chunk_edges = _valid_items(P2Edge, r.data.get("edges"))
        edges += sorted(chunk_edges, key=lambda e: -e.confidence)[:min(3 * len(chunk), 150)]
        conflicts += _valid_items(P2Conflict, r.data.get("potential_conflicts"))
    return edges, conflicts


def _valid_items(model, raw) -> list:
    out = []
    for item in raw or []:
        try:
            out.append(model.model_validate(item))
        except ValidationError:
            continue  # item-level: one bad proposal never discards the rest
    return out


# ---------------------------------------------------------------- cycles


def break_cycles(edges: list[Edge]) -> int:
    """Auto-reject the lowest-confidence LLM edge in each cycle over the acyclic relations."""
    rejected = 0
    while cycle := _find_cycle([e for e in edges if e.relation in ACYCLIC
                                and e.status not in ("rejected", "auto_rejected")]):
        llm = [e for e in cycle if e.source == "llm"]
        if not llm:
            log.warning("cycle made only of rule edges left in place")
            break
        victim = min(llm, key=lambda e: e.confidence or 0)
        victim.status, victim.reject_reason = "auto_rejected", "cycle"
        rejected += 1
    return rejected


def _find_cycle(edges: list[Edge]) -> list[Edge] | None:
    out = defaultdict(list)
    for e in edges:
        out[e.upstream_id].append(e)
    color: dict[str, int] = {}
    stack_edges: list[Edge] = []

    def dfs(n: str) -> list[Edge] | None:
        color[n] = 1
        for e in out[n]:
            m = e.downstream_id
            stack_edges.append(e)
            if color.get(m) == 1:
                i = next(i for i, x in enumerate(stack_edges) if x.upstream_id == m)
                return stack_edges[i:]
            if color.get(m) is None and (found := dfs(m)):
                return found
            stack_edges.pop()
        color[n] = 2
        return None

    for n in list(out):
        if color.get(n) is None and (found := dfs(n)):
            return found
    return None


# ---------------------------------------------------------------- orchestration


async def build_edges(contract_id: uuid.UUID, obligations, clauses, doc_text: str, page_offsets,
                      client: GeminiClient | None, enable_llm: bool) -> EdgeResult:
    edges = rule_edges(contract_id, obligations, clauses, page_offsets)
    warnings: list[str] = []
    conflicts: list[P2Conflict] = []
    if enable_llm and client is not None and len(_active(obligations)) >= 2:
        try:
            proposals, conflicts = await propose_llm_edges(client, obligations, clauses)
            llm, w = validate_llm_edges(contract_id, proposals, obligations, clauses, doc_text, page_offsets)
            warnings += w
            edges = _dedupe(edges + llm)
        except ConanError as exc:
            log.warning("p2 failed: %s", getattr(exc, "code", type(exc).__name__))
            warnings.append("AI link proposals unavailable; showing rule-based links only.")
    n = break_cycles(edges)
    if n:
        warnings.append(f"{n} AI link proposal(s) removed because they formed a cycle.")
    return EdgeResult(edges, warnings, conflicts)


def refresh_rule_edges(existing: list[Edge], fresh: list[Edge]) -> tuple[list[Edge], list[Edge]]:
    """After a reviewer edit: keep rule edges that still hold (with their review status), add new
    ones, return (to_add, to_delete). LLM edges are never touched here."""
    key = lambda e: (e.upstream_id, e.downstream_id, e.relation)  # noqa: E731
    have = {key(e): e for e in existing if e.source == "rule"}
    want = {key(e): e for e in fresh}
    to_add = [e for k, e in want.items() if k not in have]
    to_delete = [e for k, e in have.items() if k not in want]
    return to_add, to_delete
