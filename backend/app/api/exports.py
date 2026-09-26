"""ICS + CSV export (TRD §7, plan §12). ICS carries only resolved deadlines, each with VALARM reminders
7 days and 1 day before: the cheapest REAL reminder (the user's own calendar does the reminding).
Text is escaped per RFC 5545 and lines are folded at 75 octets; CSV cells are guarded against
spreadsheet formula injection.
"""

import csv
import datetime as dt
import io
import re
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlmodel import Session

from app.api.assemble import build_analysis, get_contract_or_404, resolve_as_of
from app.db import get_session
from app.schemas import DISCLAIMER

router = APIRouter(prefix="/api")


def _ics_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n"))


def _fold(line: str) -> str:
    """RFC 5545 §3.1: lines over 75 octets continue on the next line after CRLF + space."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")[:60] or "contract"


@router.get("/contracts/{contract_id}/export.ics")
def export_ics(contract_id: uuid.UUID, as_of: dt.date | None = None, s: Session = Depends(get_session)) -> Response:
    contract = get_contract_or_404(s, contract_id)
    a = build_analysis(s, contract, resolve_as_of(as_of), False)
    sections = {c.id: c.section_ref or c.id for c in a.clauses}
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Conan//Obligation deadlines//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{_ics_escape('Conan: ' + contract.name)}"]
    for o in a.obligations:
        if o.status in ("done", "waived") or o.review_state == "rejected" or o.due_date is None:
            continue
        dates = o.next_occurrences or [o.due_date]
        for n, day in enumerate(dates):
            summary = f"{o.actor}: {o.action} {o.object or ''}".strip()
            desc = "\n".join(filter(None, [
                f"{o.id} · §{sections.get(o.clause_id, '?')} · p. {o.page_start}"
                + (" (approx.)" if o.page_approx else ""),
                f"\"{o.evidence_quote}\"",
                f"Deadline: {o.resolution_trace}" if o.resolution_trace else None,
                f"Attention priority: {o.risk.score} ({o.risk.band}) — not a probability of breach",
                DISCLAIMER,
            ]))
            lines += [
                "BEGIN:VEVENT",
                f"UID:{contract.id}-{o.id}-{n}@conan",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{(day + dt.timedelta(days=1)).strftime('%Y%m%d')}",
                f"SUMMARY:{_ics_escape('[Conan] ' + summary)}",
                f"DESCRIPTION:{_ics_escape(desc)}",
            ]
            for trigger, label in (("-P7D", "in 7 days"), ("-P1D", "tomorrow")):
                lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER:{trigger}",
                          f"DESCRIPTION:{_ics_escape(f'Due {label}: {summary}')}", "END:VALARM"]
            lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    body = "\r\n".join(_fold(line) for line in lines) + "\r\n"
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{_slug(contract.name)}.ics"'})


_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _cell(v) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(_FORMULA) else s  # stop spreadsheets from executing cell text


@router.get("/contracts/{contract_id}/export.csv")
def export_csv(contract_id: uuid.UUID, as_of: dt.date | None = None, s: Session = Depends(get_session)) -> Response:
    contract = get_contract_or_404(s, contract_id)
    a = build_analysis(s, contract, resolve_as_of(as_of), False)
    sections = {c.id: c.section_ref or c.id for c in a.clauses}
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["id", "section", "page", "page_approx", "actor", "modality", "action", "object", "category",
                "counterparty", "due_date", "deadline_status", "deadline_trace", "date_provenance",
                "attention_priority", "band", "review_state", "status", "evidence_status", "evidence_quote"])
    for o in a.obligations:
        w.writerow([_cell(v) for v in (
            o.id, sections.get(o.clause_id), o.page_start, o.page_approx, o.actor, o.modality, o.action, o.object,
            o.category, o.counterparty, o.due_date, o.resolution_status, o.resolution_trace, o.date_provenance,
            o.risk.score, o.risk.band, o.review_state, o.status, o.evidence_status, o.evidence_quote)])
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",  # BOM: Excel opens UTF-8 right
                    headers={"Content-Disposition": f'attachment; filename="{_slug(contract.name)}.csv"'})
