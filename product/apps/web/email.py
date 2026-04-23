"""OTP email delivery.

Backend preference order (first configured wins):
  1. Resend   — RESEND_API_KEY set
  2. AWS SES  — SES_FROM_ADDRESS set (blocked on production-access review)
  3. SMTP     — SMTP_HOST set (local dev / mailpit / Brevo-style relays)

Env:
  RESEND_API_KEY     re_xxx... (preferred; Resend is active in prod)
  RESEND_FROM        "Benji <noreply@finadvisor.gkamal.online>" (default)
  SES_FROM_ADDRESS   fallback SES sender
  SES_REGION         default "us-east-1"
  SMTP_*             local fallback — see subprime.core.config
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

from subprime.core.config import SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
RESEND_FROM = os.environ.get("RESEND_FROM") or os.environ.get(
    "SES_FROM_ADDRESS", "Benji <noreply@finadvisor.gkamal.online>"
)
SES_FROM_ADDRESS = os.environ.get("SES_FROM_ADDRESS")
SES_REGION = os.environ.get("SES_REGION", "us-east-1")


async def send_otp_email(email: str, code: str) -> bool:
    """Send an OTP code. Returns True on success, False on any failure.

    Dispatches to Resend, else SES, else SMTP, else no-op with warning.
    """
    if RESEND_API_KEY:
        if await _send_via_resend(email, code):
            return True
        logger.warning("Resend send failed for %s; trying SES", email)

    if SES_FROM_ADDRESS:
        if await _send_via_ses(email, code):
            return True
        logger.warning("SES send failed for %s; falling back to SMTP", email)

    if SMTP_HOST:
        return _send_via_smtp(email, code)

    logger.warning(
        "No email backend configured (set RESEND_API_KEY, SES_FROM_ADDRESS, or SMTP_HOST)"
        " — cannot send OTP to %s",
        email,
    )
    return False


# ── Resend (preferred) ────────────────────────────────────────────────────────


async def _send_via_resend(to_email: str, code: str) -> bool:
    """POST to Resend's /emails endpoint.

    Uses httpx directly — a full ``resend`` SDK dependency isn't needed for a
    single endpoint and their API is trivially JSON-in-JSON-out.
    """
    import httpx

    text, html = _format_email(code, to_email)
    payload = {
        "from": RESEND_FROM,
        "to": [to_email],
        "subject": _OTP_SUBJECT,
        "text": text,
        "html": html,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if r.status_code >= 300:
            logger.warning(
                "Resend send failed for %s: HTTP %s %s", to_email, r.status_code, r.text[:200]
            )
            return False
        logger.info("Resend OTP sent to %s (id=%s)", to_email, r.json().get("id"))
        return True
    except Exception:
        logger.exception("Resend POST raised for %s", to_email)
        return False


# ── SES (preferred) ───────────────────────────────────────────────────────────

APP_URL = os.environ.get("APP_URL", "https://finadvisor.gkamal.online")
_OTP_SUBJECT = "Your Benji Premium Code"
_OTP_TEXT = (
    "Your one-time code: {code}\n\n"
    "Click to continue: {link}\n\n"
    "Or enter the code at {app} to unlock Premium.\n"
    "Expires in 10 minutes.\n\n"
    "— Benji"
)
_OTP_HTML = (
    "<div style='font-family:system-ui,-apple-system,sans-serif;max-width:480px'>"
    "<p style='color:#0f172a;margin:0 0 4px'>Your one-time code:</p>"
    "<p style='font-size:32px;letter-spacing:8px;font-family:ui-monospace,monospace;"
    "color:#dc2626;font-weight:700;margin:4px 0 20px'>{code}</p>"
    "<p style='margin:0 0 20px'>"
    "<a href='{link}' style='display:inline-block;background:#dc2626;color:#fff;"
    "text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:600;"
    "font-size:15px'>Click to continue →</a>"
    "</p>"
    "<p style='color:#64748b;font-size:13px;margin:0 0 4px'>"
    "Or paste the code at <a href='{app}' style='color:#dc2626'>{app_host}</a> "
    "— expires in 10 minutes.</p>"
    "<p style='color:#94a3b8;font-size:12px;margin-top:24px'>— Benji</p>"
    "</div>"
)


def _format_email(code: str, email: str) -> tuple[str, str]:
    """Return (text, html) with code + magic link filled in."""
    from urllib.parse import quote

    link = f"{APP_URL}/verify?email={quote(email)}&code={quote(code)}"
    app_host = APP_URL.replace("https://", "").replace("http://", "").rstrip("/")
    text = _OTP_TEXT.format(code=code, link=link, app=APP_URL)
    html = _OTP_HTML.format(code=code, link=link, app=APP_URL, app_host=app_host)
    return text, html


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
            text, html = _format_email(code, to_email)
            client.send_email(
                Source=SES_FROM_ADDRESS,
                Destination={"ToAddresses": [to_email]},
                Message={
                    "Subject": {"Charset": "UTF-8", "Data": _OTP_SUBJECT},
                    "Body": {
                        "Text": {"Charset": "UTF-8", "Data": text},
                        "Html": {"Charset": "UTF-8", "Data": html},
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
    text, html = _format_email(code, to_email)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

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
