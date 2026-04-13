"""SMTP email sending for OTP codes."""
from __future__ import annotations
import logging
import smtplib
from email.message import EmailMessage
from subprime.core.config import SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER

logger = logging.getLogger(__name__)

async def send_otp_email(email: str, code: str) -> bool:
    """Send an OTP code via SMTP. Returns True on success."""
    if not SMTP_HOST:
        logger.warning("SMTP not configured — cannot send OTP to %s", email)
        return False

    msg = EmailMessage()
    msg["Subject"] = "Your FinAdvisor Premium Code"
    msg["From"] = SMTP_FROM
    msg["To"] = email
    msg.set_content(
        f"Your one-time code: {code}\n\n"
        f"Enter this code at https://finadvisor.gkamal.online to start your premium plan.\n"
        f"This code expires in 10 minutes.\n\n"
        f"— FinAdvisor"
    )

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            if SMTP_USER and SMTP_PASSWORD:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("OTP email sent to %s", email)
        return True
    except Exception:
        logger.exception("Failed to send OTP email to %s", email)
        return False
