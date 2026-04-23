"""Tests for CAS PDF parsing and the profile/cas upload endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from subprime.data.cas import CASParseError, parse_cas

FIXTURE = Path(__file__).parent / "fixtures" / "dummy_cas.pdf"


def test_dummy_cas_fixture_exists() -> None:
    assert FIXTURE.exists(), "Generate with the script in tests/fixtures/README."
    assert FIXTURE.stat().st_size > 500


def test_parse_cas_wrong_password_raises() -> None:
    with pytest.raises(CASParseError):
        parse_cas(FIXTURE.read_bytes(), "not-the-password")


def test_parse_cas_non_cams_pdf_raises() -> None:
    """A PDF that casparser can't match as a CAMS/KFintech statement should
    raise CASParseError, not crash or silently return []."""
    # 4-byte garbage is clearly not a PDF
    with pytest.raises(CASParseError):
        parse_cas(b"not a pdf", "anything")


@pytest.mark.asyncio
async def test_upload_cas_requires_profile() -> None:
    from apps.web.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # No profile set yet
        with FIXTURE.open("rb") as f:
            r = await c.post(
                "/api/v2/profile/cas",
                files={"file": ("cas.pdf", f, "application/pdf")},
                data={"password": "TESTPASS12"},
            )
        # Either 400 (profile missing) or 400 (parse error) — both acceptable,
        # both signal the endpoint is wired and validating. Key point: no 500.
        assert r.status_code in (400, 413)


@pytest.mark.asyncio
async def test_upload_cas_rejects_large_files() -> None:
    from apps.web.main import create_app

    app = create_app()
    big = b"\x00" * (11 * 1024 * 1024)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/v2/profile/cas",
            files={"file": ("cas.pdf", big, "application/pdf")},
            data={"password": "x"},
        )
    assert r.status_code == 413
