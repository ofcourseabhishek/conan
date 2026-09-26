"""Test email reminder: off by default, one validated recipient, fixed escaped template, rate limits,
no address in logs, provider errors surfaced without leaking."""

import logging

import pytest

from app.api import reminders
from app.config import get_settings
from tests.test_review import AS_OF, seeded  # noqa: F401  (fixture re-use)


@pytest.fixture()
def enabled(monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "enable_reminders", True)
    monkeypatch.setattr(st, "resend_api_key", "re_test")
    reminders.per_ip.clear()
    reminders.per_day.clear()
    sent = []

    async def fake_send(to, subject, text, html_body):
        sent.append({"to": to, "subject": subject, "text": text, "html": html_body})
        return "msg_1"

    monkeypatch.setattr(reminders, "send_email", fake_send)
    return sent


def remind(client, cid, oid="O-004", email="owner@example.com"):
    return client.post(f"/api/obligations/{oid}/remind", params={"contract_id": cid, **AS_OF}, json={"email": email})


def test_disabled_by_default(seeded):  # noqa: F811
    client, cid, _ = seeded
    r = remind(client, cid)
    assert r.status_code == 503 and "not enabled" in r.json()["detail"]


def test_sends_one_fixed_template(seeded, enabled):  # noqa: F811
    client, cid, _ = seeded
    client.put(f"/api/contracts/{cid}/events/invoice_receipt", json={"date": "2026-10-03"})
    r = remind(client, cid)
    assert r.status_code == 200 and r.json()["sent"] is True
    [m] = enabled
    assert m["to"] == "owner@example.com"
    assert m["subject"].startswith("[Conan test reminder] Velloran Components LLP: pay")
    assert m["subject"].endswith("(due 02 Nov 2026)")
    assert "Attention priority" in m["text"] and "not legal advice" in m["text"] and "scheduled worker" in m["text"]


@pytest.mark.parametrize("bad", ["not-an-email", "a@b.com, c@d.com", "a@b.com\r\nBcc: x@y.com", "Name <a@b.com>",
                                 "a@b", "a b@c.com", "@b.com"])
def test_rejects_anything_but_one_plain_address(seeded, enabled, bad):  # noqa: F811
    client, cid, _ = seeded
    assert remind(client, cid, email=bad).status_code == 422 and enabled == []


def test_html_is_escaped(seeded, enabled):  # noqa: F811
    client, cid, _ = seeded
    client.patch("/api/obligations/O-004", params={"contract_id": cid},
                 json={"action": "edit", "patch": {"action": "<script>alert(1)</script>"}})
    assert remind(client, cid).status_code == 200
    assert "<script>" not in enabled[0]["html"] and "&lt;script&gt;" in enabled[0]["html"]


def test_rate_limits(seeded, enabled, monkeypatch):  # noqa: F811
    client, cid, _ = seeded
    assert [remind(client, cid).status_code for _ in range(4)] == [200, 200, 200, 429]
    reminders.per_ip.clear()
    monkeypatch.setattr(get_settings(), "reminders_per_day", 3)
    r = remind(client, cid)
    assert r.status_code == 429 and "quota" in r.json()["detail"]


def test_unknown_obligation_and_provider_error_without_leaking_address(seeded, enabled, monkeypatch, caplog):  # noqa: F811
    client, cid, _ = seeded
    assert remind(client, cid, oid="O-999").status_code == 404

    async def boom(*a):
        raise RuntimeError("resend 403: You can only send testing emails to your own email address")

    monkeypatch.setattr(reminders, "send_email", boom)
    with caplog.at_level(logging.INFO, logger="conan.remind"):
        r = remind(client, cid, email="secret.person@example.com")
    assert r.status_code == 502 and "own account address" in r.json()["detail"]
    assert "secret.person" not in caplog.text


def test_subject_without_a_due_date(seeded, enabled):  # noqa: F811
    client, cid, _ = seeded
    assert remind(client, cid).status_code == 200
    assert enabled[0]["subject"].endswith("(no due date yet)") and "due no due" not in enabled[0]["subject"]
