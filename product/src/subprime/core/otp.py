# src/subprime/core/otp.py
"""OTP generation and verification for the premium tier gate.

6-digit codes, 10-minute expiry, 100/day limit.
One active OTP per email (new request invalidates old).
"""

from __future__ import annotations
import logging
import secrets
from datetime import datetime, timedelta, timezone
from subprime.core.config import OTP_DAILY_LIMIT, OTP_EXPIRY_MINUTES

logger = logging.getLogger(__name__)


async def create_otp(pool, email: str) -> dict:
    """Generate a 6-digit OTP.
    Returns {"success": True, "code": "123456"} or {"success": False, "reason": "..."}.
    """
    count = await daily_otp_count(pool)
    if count >= OTP_DAILY_LIMIT:
        return {
            "success": False,
            "reason": "Premium slots are full for today — try again tomorrow.",
        }

    # Invalidate existing unexpired OTPs for this email
    await pool.execute(
        "UPDATE otps SET verified_at = NOW() WHERE email = $1 AND verified_at IS NULL AND expires_at > NOW()",
        email,
    )

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)

    await pool.execute(
        "INSERT INTO otps (email, code, expires_at) VALUES ($1, $2, $3)",
        email,
        code,
        expires_at,
    )

    logger.info("OTP created for %s (daily count: %d)", email, count + 1)
    return {"success": True, "code": code}


async def verify_otp(pool, email: str, code: str) -> bool:
    """Verify an OTP code. Returns True if valid."""
    row = await pool.fetchrow(
        "SELECT id, email, code, expires_at, verified_at FROM otps WHERE email = $1 AND code = $2 ORDER BY created_at DESC LIMIT 1",
        email,
        code,
    )
    if not row:
        return False
    if row["verified_at"] is not None:
        return False
    if row["expires_at"] < datetime.now(timezone.utc):
        return False

    await pool.execute("UPDATE otps SET verified_at = NOW() WHERE id = $1", row["id"])
    logger.info("OTP verified for %s", email)
    return True


async def daily_otp_count(pool) -> int:
    """Count OTPs created today (UTC)."""
    count = await pool.fetchval("SELECT COUNT(*) FROM otps WHERE created_at >= CURRENT_DATE")
    return count or 0
