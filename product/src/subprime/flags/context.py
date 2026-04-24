"""Attribute builder for feature-flag evaluation.

Pulls out everything we have about the current request + session so
flag rules can target by email, domain, country, tier, bot-likelihood,
session id, or hashed IP — see the module docstring of ``subprime.flags``
for example rule JSON.

Attributes produced (all optional except session_id):

  session_id      str   random, stable per wizard session
  email           str   set after OTP verify (premium only)
  email_domain    str   derived from email, lowercase
  tier            str   "basic" | "premium"
  is_demo         bool  OTP cheat code was used
  country         str   Cloudflare cf-ipcountry (ISO-2)
  user_agent      str   raw User-Agent
  is_likely_bot   bool  crude UA + Client-Hints heuristic
  ip_hash         str   SHA-256(cf-connecting-ip)[:16] — raw IP never
                         leaves this module
  request_id      str   cf-ray; useful for audit correlation
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import Request

    from subprime.core.models import Session


_BOT_UA_TOKENS = (
    "bot",
    "crawl",
    "spider",
    "curl/",
    "wget/",
    "python-",
    "httpx/",
    "go-http-client",
    "scrapy",
    "phantomjs",
    "headlesschrome",
)


def _is_likely_bot(user_agent: str | None, headers: Any) -> bool:
    """Crude bot heuristic.

    Works without Cloudflare Bot Management. Flags:
      - empty or obvious bot-ish User-Agent
      - missing Accept-Language (real browsers always send it)
      - missing sec-fetch-* (real browsers send these on navigations)
    Returns False for anything ambiguous so we don't accidentally
    exclude low-end mobile browsers.
    """
    ua = (user_agent or "").lower().strip()
    if not ua:
        return True
    if any(tok in ua for tok in _BOT_UA_TOKENS):
        return True
    if not headers.get("accept-language"):
        return True
    return False


def _hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]


def flag_ctx(request: "Request | None", session: "Session | None") -> dict[str, Any]:
    """Build the attribute dict for ``is_on(..., ctx=flag_ctx(...))``.

    Both args are optional — what we can't fill in stays out of the
    dict, rather than showing up as empty strings that break
    ``$in`` / ``$regex`` matches.
    """
    attrs: dict[str, Any] = {}

    if session is not None:
        attrs["session_id"] = session.id
        attrs["tier"] = session.mode
        attrs["is_demo"] = bool(session.is_demo)
        if session.email:
            attrs["email"] = session.email
            if "@" in session.email:
                attrs["email_domain"] = session.email.split("@", 1)[1].lower()

    if request is not None:
        headers = request.headers
        ua = headers.get("user-agent")
        if ua:
            attrs["user_agent"] = ua
        country = headers.get("cf-ipcountry")
        if country and country != "XX":  # XX = Cloudflare's 'unknown'
            attrs["country"] = country
        ip_hash = _hash_ip(
            headers.get("cf-connecting-ip") or (request.client.host if request.client else None)
        )
        if ip_hash:
            attrs["ip_hash"] = ip_hash
        ray = headers.get("cf-ray")
        if ray:
            attrs["request_id"] = ray
        attrs["is_likely_bot"] = _is_likely_bot(ua, headers)
        # Cloudflare Bot Management (Pro+) sets cf-bot-score 1-99; lower = more bot-like.
        bs = headers.get("cf-bot-score")
        if bs:
            try:
                attrs["cf_bot_score"] = int(bs)
            except ValueError:
                pass

    return attrs
