"""Stretch: one real "Send test reminder" email per click, via Resend (plan §12, §15).

Not an open relay:
- exactly one recipient, the address typed in, validated so it cannot smuggle headers or extra recipients;
- the body is a fixed server-side template built from the obligation, so no caller-supplied text is sent;
- 3 per hour per IP and a global daily cap; off unless ENABLE_REMINDERS=true and RESEND_API_KEY is set.
Email addresses are never logged. There is no scheduler: production would use a scheduled worker.
"""

import datetime as dt
import html
import logging
import re
import time
import uuid
from collections import defaultdict, deque

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from app.api.assemble import build_analysis, get_contract_or_404, resolve_as_of
from app.config import get_settings
from app.db import get_session
from app.schemas import DISCLAIMER, RemindRequest, RemindResponse

router = APIRouter(prefix="/api")
log = logging.getLogger("conan.remind")

RESEND_URL = "https://api.resend.com/emails"
# One plain address: no spaces, commas, angle brackets, quotes or line breaks (header/recipient injection).
_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?"
                    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)+$")
_per_ip: dict[str, deque] = defaultdict(deque)
_per_day: deque = deque()


def _allow(ip: str) -> str | None:
    """Returns a refusal message, or None if this send is allowed (and records it)."""
    st, now = get_settings(), time.monotonic()
    q = _per_ip[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    while _per_day and now - _per_day[0] > 86400:
        _per_day.popleft()
    if len(q) >= st.reminders_per_ip_hour:
        return f"Limit reached: {st.reminders_per_ip_hour} test reminders per hour."
    if len(_per_day) >= st.reminders_per_day:
        return "Today's test-reminder quota is used up."
    q.append(now)
    _per_day.append(now)
    return None


async def send_email(to: str, subject: str, text: str, html_body: str) -> str:
    """Resend HTTP API. Returns the Resend message id. Replaced by a fake in tests."""
    st = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(RESEND_URL, headers={"Authorization": f"Bearer {st.resend_api_key}"},
                              json={"from": st.reminder_from, "to": [to], "subject": subject,
                                    "text": text, "html": html_body})
    if r.status_code >= 400:
        raise RuntimeError(f"resend {r.status_code}: {r.text[:200]}")
    return r.json().get("id", "")


def compose(contract_name: str, o, section: str) -> tuple[str, str, str]:
    due = o.due_date.strftime("%d %b %Y") if o.due_date else "no due date yet"
    what = f"{o.actor}: {o.action} {o.object or ''}".strip()
    subject = f"[Conan test reminder] {what[:90]} ({'due ' + due if o.due_date else due})"
    rows = [
        ("Contract", contract_name),
        ("Obligation", f"{o.id} · §{section} · page {o.page_start}" + (" (approx.)" if o.page_approx else "")),
        ("Due", due + (f" — {o.resolution_trace}" if o.resolution_trace else "")),
        ("Attention priority", f"{o.risk.score} ({o.risk.band}), not a probability of breach"),
        ("Source text", f"“{o.evidence_quote}”"),
    ]
    footer = ("This is a one-off test reminder sent from the Conan demo. In production, reminders come from a "
              "scheduled worker. " + DISCLAIMER)
    text = f"{what}\n\n" + "\n".join(f"{k}: {v}" for k, v in rows) + f"\n\n{footer}\n"
    e = html.escape  # contract text and LLM output are untrusted: never interpolate raw into HTML
    html_body = (
        f"<div style=\"font-family:system-ui,sans-serif;max-width:560px\"><h2 style=\"font-size:18px\">{e(what)}</h2>"
        "<table style=\"border-collapse:collapse;font-size:14px\">"
        + "".join(f"<tr><td style=\"padding:4px 12px 4px 0;color:#5a6475;vertical-align:top\">{e(k)}</td>"
                  f"<td style=\"padding:4px 0\">{e(v)}</td></tr>" for k, v in rows)
        + f"</table><p style=\"font-size:12px;color:#5a6475;margin-top:16px\">{e(footer)}</p></div>")
    return subject, text, html_body


@router.post("/obligations/{obligation_id}/remind", response_model=RemindResponse)
async def remind(obligation_id: str, body: RemindRequest, contract_id: uuid.UUID, request: Request,
                 as_of: dt.date | None = None, s: Session = Depends(get_session)) -> RemindResponse:
    st = get_settings()
    if not st.enable_reminders or not st.resend_api_key:
        raise HTTPException(status_code=503, detail="Test reminders are not enabled on this server.")
    email = body.email.strip()
    if not _EMAIL.match(email):
        raise HTTPException(status_code=422, detail="Enter one valid email address.")
    contract = get_contract_or_404(s, contract_id)
    a = build_analysis(s, contract, resolve_as_of(as_of), False)
    o = next((x for x in a.obligations if x.id == obligation_id), None)
    if o is None:
        raise HTTPException(status_code=404, detail="Obligation not found")
    if refusal := _allow(request.client.host if request.client else "unknown"):
        raise HTTPException(status_code=429, detail=refusal)
    section = next((c.section_ref or c.id for c in a.clauses if c.id == o.clause_id), "?")
    subject, text, html_body = compose(contract.name, o, section)
    try:
        await send_email(email, subject, text, html_body)
    except Exception as exc:  # noqa: BLE001
        log.warning("reminder failed obligation=%s err=%s", o.id, type(exc).__name__)  # no address in logs
        raise HTTPException(status_code=502, detail="The email service rejected the message. "
                            "On Resend's free tier you can only send to your own account address.") from exc
    log.info("reminder sent obligation=%s contract=%s", o.id, contract.id)
    return RemindResponse(sent=True, message="Test reminder sent. Check your inbox (and spam folder).")
