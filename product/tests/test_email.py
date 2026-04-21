"""Tests for the OTP email dispatcher.

Branching rule:
  - SES_FROM_ADDRESS set + SES call succeeds → SES path, no SMTP.
  - SES_FROM_ADDRESS set + SES fails          → SMTP fallback.
  - SES_FROM_ADDRESS unset + SMTP_HOST set    → SMTP path only.
  - Neither set                               → no-op, returns False.
"""
from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest


def _reload(monkeypatch, **env):
    # Clear + set the three env vars that steer dispatch, then reimport
    # apps.web.email so module-level constants pick up the new values.
    for k in ("SES_FROM_ADDRESS", "SES_REGION", "SMTP_HOST"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        if v is None:
            continue
        monkeypatch.setenv(k, v)
    import apps.web.email as mod
    return importlib.reload(mod)


@pytest.mark.asyncio
async def test_no_backend_returns_false(monkeypatch, caplog):
    mod = _reload(monkeypatch)
    with patch("subprime.core.config.SMTP_HOST", None):
        ok = await mod.send_otp_email("u@example.com", "123456")
    assert ok is False


@pytest.mark.asyncio
async def test_ses_primary_path_used_when_configured(monkeypatch):
    mod = _reload(monkeypatch, SES_FROM_ADDRESS="sender@example.com")
    ses_client = MagicMock()
    ses_client.send_email = MagicMock(return_value={"MessageId": "abc"})
    with patch("boto3.client", return_value=ses_client):
        ok = await mod.send_otp_email("u@example.com", "123456")
    assert ok is True
    ses_client.send_email.assert_called_once()
    call = ses_client.send_email.call_args.kwargs
    assert call["Source"] == "sender@example.com"
    assert call["Destination"] == {"ToAddresses": ["u@example.com"]}
    body = call["Message"]["Body"]
    assert "123456" in body["Text"]["Data"]
    assert "123456" in body["Html"]["Data"]


@pytest.mark.asyncio
async def test_ses_failure_falls_back_to_smtp(monkeypatch):
    mod = _reload(monkeypatch,
                  SES_FROM_ADDRESS="sender@example.com",
                  SMTP_HOST="mailpit.local")
    ses_client = MagicMock()
    ses_client.send_email = MagicMock(side_effect=RuntimeError("sandbox"))
    smtp_server = MagicMock()
    smtp_ctx = MagicMock()
    smtp_ctx.__enter__ = MagicMock(return_value=smtp_server)
    smtp_ctx.__exit__ = MagicMock(return_value=False)
    with patch("boto3.client", return_value=ses_client), \
         patch("subprime.core.config.SMTP_HOST", "mailpit.local"), \
         patch("apps.web.email.SMTP_HOST", "mailpit.local"), \
         patch("smtplib.SMTP", return_value=smtp_ctx):
        ok = await mod.send_otp_email("u@example.com", "123456")
    assert ok is True
    ses_client.send_email.assert_called_once()
    smtp_server.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_smtp_only_when_ses_not_configured(monkeypatch):
    mod = _reload(monkeypatch, SMTP_HOST="mailpit.local")
    smtp_server = MagicMock()
    smtp_ctx = MagicMock()
    smtp_ctx.__enter__ = MagicMock(return_value=smtp_server)
    smtp_ctx.__exit__ = MagicMock(return_value=False)
    with patch("apps.web.email.SMTP_HOST", "mailpit.local"), \
         patch("boto3.client") as boto, \
         patch("smtplib.SMTP", return_value=smtp_ctx):
        ok = await mod.send_otp_email("u@example.com", "123456")
    assert ok is True
    boto.assert_not_called()        # SES path skipped
    smtp_server.send_message.assert_called_once()
