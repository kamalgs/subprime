"""OTP email delivery.

Prefers AWS SES when ``SES_FROM_ADDRESS`` is configured — production path.
Falls back to SMTP (existing ``SMTP_HOST``) when SES isn't available —
used by local dev against mailpit and in any env where SES hasn't been
verified yet.

SES setup checklist:
  1. Verify the sender (domain or address) in the target region.
     `aws ses verify-domain-identity --domain gkamal.online`
     `aws ses verify-email-identity --email noreply@finadvisor.gkamal.online`
  2. Add DKIM CNAMEs printed by `aws ses get-identity-dkim-attributes` to
     the DNS provider (Cloudflare for gkamal.online).
  3. Request production access when ready — until then sandbox only lets
     you send to verified addresses.

Env:
  SES_FROM_ADDRESS   "Benji <noreply@finadvisor.gkamal.online>" (required for SES path)
  SES_REGION         default "us-east-1"
  SMTP_*             legacy fallback — see subprime.core.config
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

from subprime.core.config import SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER

logger = logging.getLogger(__name__)

SES_FROM_ADDRESS = os.environ.get("SES_FROM_ADDRESS")
SES_REGION = os.environ.get("SES_REGION", "us-east-1")


async def send_otp_email(email: str, code: str) -> bool:
    """Send an OTP code. Returns True on success, False on any failure.

    Dispatches to SES when configured, else SMTP, else no-op with warning.
    """
    if SES_FROM_ADDRESS:
        if await _send_via_ses(email, code):
            return True
        logger.warning("SES send failed for %s; falling back to SMTP", email)

    if SMTP_HOST:
        return _send_via_smtp(email, code)

    logger.warning("No email backend configured (set SES_FROM_ADDRESS or "
                   "SMTP_HOST) — cannot send OTP to %s", email)
    return False


# ── SES (preferred) ───────────────────────────────────────────────────────────

_OTP_SUBJECT = "Your Benji Premium Code"
_OTP_TEXT = (
    "Your one-time code: {code}\n\n"
    "Enter it at https://finadvisor.gkamal.online to unlock Premium.\n"
    "Code expires in 10 minutes.\n\n"
    "— Benji"
)
_OTP_HTML = (
    "<p>Your one-time code:</p>"
    "<p style='font-size:28px;letter-spacing:6px;font-family:ui-monospace,monospace;"
    "color:#dc2626;font-weight:700'>{code}</p>"
    "<p>Enter it at <a href='https://finadvisor.gkamal.online'>"
    "finadvisor.gkamal.online</a> to unlock Premium. Expires in 10 minutes.</p>"
    "<p style='color:#64748b;font-size:12px'>— Benji</p>"
)


async def _send_via_ses(to_email: str, code: str) -> bool:
    """boto3 SES SendEmail. Runs in a thread so we don't block the event
    loop — boto3 is sync, aioboto3 is a heavier dep than warranted."""
    import asyncio

    def _send_sync() -> bool:
        try:
            import boto3
        except ImportError:
            logger.warning("boto3 not installed; cannot use SES")
            return False
        try:
            client = boto3.client("ses", region_name=SES_REGION)
            client.send_email(
                Source=SES_FROM_ADDRESS,
                Destination={"ToAddresses": [to_email]},
                Message={
                    "Subject": {"Charset": "UTF-8", "Data": _OTP_SUBJECT},
                    "Body": {
                        "Text": {"Charset": "UTF-8",
                                 "Data": _OTP_TEXT.format(code=code)},
                        "Html": {"Charset": "UTF-8",
                                 "Data": _OTP_HTML.format(code=code)},
                    },
                },
            )
            logger.info("SES OTP sent to %s (region=%s)", to_email, SES_REGION)
            return True
        except Exception:
            logger.exception("SES send_email failed for %s", to_email)
            return False

    return await asyncio.to_thread(_send_sync)


# ── SMTP (legacy fallback) ────────────────────────────────────────────────────

def _send_via_smtp(to_email: str, code: str) -> bool:
    msg = EmailMessage()
    msg["Subject"] = _OTP_SUBJECT
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.set_content(_OTP_TEXT.format(code=code))
    msg.add_alternative(_OTP_HTML.format(code=code), subtype="html")

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            if SMTP_USER and SMTP_PASSWORD:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("SMTP OTP sent to %s (host=%s)", to_email, SMTP_HOST)
        return True
    except Exception:
        logger.exception("SMTP send failed for %s", to_email)
        return False
