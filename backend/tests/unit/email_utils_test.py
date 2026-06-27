import logging
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.utils import email_utils


@pytest.fixture
def smtp_config(monkeypatch):
    monkeypatch.setitem(email_utils.SMTP_CONFIG, "hostname", "mailpit")
    monkeypatch.setitem(email_utils.SMTP_CONFIG, "port", 1025)
    monkeypatch.setitem(email_utils.SMTP_CONFIG, "username", "pipeliner@example.com")
    monkeypatch.setitem(email_utils.SMTP_CONFIG, "password", "pipeliner")
    monkeypatch.setitem(email_utils.SMTP_CONFIG, "use_tls", False)
    monkeypatch.setattr(email_utils, "FIXED_RECIPIENT", "admin@example.com")


@pytest.mark.asyncio
async def test_send_lockout_alert_to_local_smtp(smtp_config):
    send = AsyncMock()

    with patch.object(email_utils.aiosmtplib, "send", send):
        await email_utils.send_lockout_alert("locked-user")

    send.assert_awaited_once()
    message = send.await_args.args[0]
    assert message["To"] == "admin@example.com"
    assert message["Subject"] == "User Lockout: locked-user"
    assert "locked-user" in message.get_content()
    assert send.await_args.kwargs == {
        "hostname": "mailpit",
        "port": 1025,
        "username": "pipeliner@example.com",
        "password": "pipeliner",
        "use_tls": False,
    }


@pytest.mark.asyncio
async def test_send_lockout_alert_logs_failure_without_success(smtp_config, caplog):
    send = AsyncMock(side_effect=RuntimeError("SMTP unavailable"))

    with patch.object(email_utils.aiosmtplib, "send", send):
        with caplog.at_level(logging.INFO):
            await email_utils.send_lockout_alert("locked-user")

    assert "Failed to send lockout email about user: locked-user" in caplog.text
    assert "Sent lockout email about user" not in caplog.text


@pytest.mark.asyncio
async def test_send_lockout_alert_skips_without_credentials(monkeypatch, caplog):
    monkeypatch.setitem(email_utils.SMTP_CONFIG, "username", "")
    monkeypatch.setitem(email_utils.SMTP_CONFIG, "password", "")
    send = AsyncMock()

    with patch.object(email_utils.aiosmtplib, "send", send):
        with caplog.at_level(logging.WARNING):
            await email_utils.send_lockout_alert("locked-user")

    send.assert_not_awaited()
    assert "SMTP not configured" in caplog.text
