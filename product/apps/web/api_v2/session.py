"""Session lifecycle endpoints — tier, profile, persona, OTP, reset."""

from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import (
    APIRouter,
    Cookie,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)

from pydantic import BaseModel

from apps.web.api_v2._session import COOKIE_NAME, get_or_create, set_cookie
from apps.web.api_v2.dto import (
    OTPRequestBody,
    OTPSendResponse,
    OTPVerifyBody,
    OTPVerifyResponse,
    PersonaSelectBody,
    ProfileBody,
    SessionSummaryResponse,
    TierBody,
)
from subprime.core.db import get_pool
from subprime.core.models import InvestorProfile, Session
from subprime.core.otp import create_otp, verify_otp
from subprime.evaluation.personas import get_persona

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/session")
async def get_session(
    request: Request,
    response: Response,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> SessionSummaryResponse:
    """Return current session state. Creates a new session if cookie missing."""
    s = await get_or_create(request, benji_session)
    set_cookie(response, s.id)
    return SessionSummaryResponse.from_session(s)


@router.post("/session/tier", status_code=status.HTTP_200_OK)
async def set_tier(
    body: TierBody,
    request: Request,
    response: Response,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> SessionSummaryResponse:
    """Switch between basic/premium tier.

    Picking the basic tier also drops the ``is_demo`` flag — tier selection
    is the user declaring intent to start a fresh consumer flow, so we don't
    carry over the 25-persona research bank from an earlier demo unlock.
    The cheat-code → demo-mode unlock has to be re-done (which is fine).
    """
    s = await get_or_create(request, benji_session)
    s.mode = body.mode
    if body.mode == "basic":
        s.is_demo = False
    if s.current_step < 2:
        s.current_step = 2
    await request.app.state.session_store.save(s)
    set_cookie(response, s.id)
    return SessionSummaryResponse.from_session(s)


@router.post("/profile/cas")
async def upload_cas(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    password: str = Form(...),
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> dict:
    """Parse an uploaded CAMS/KFintech CAS PDF and attach holdings to the session.

    Body is multipart: ``file`` (PDF) + ``password`` (PAN or DOB, whichever
    CAMS/KFintech used to encrypt the statement).

    The PDF is never written to disk beyond a private tempfile that
    ``casparser`` reads and we discard immediately.
    """
    from subprime.data.cas import CASParseError, parse_cas

    s = await get_or_create(request, benji_session)
    pdf_bytes = await file.read()
    if len(pdf_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, "CAS PDF larger than 10 MB — refuse.")
    try:
        holdings = parse_cas(pdf_bytes, password.strip())
    except CASParseError as e:
        raise HTTPException(400, f"Couldn't parse CAS: {e}")

    if s.profile is None:
        raise HTTPException(400, "Submit the profile form first, then upload a CAS.")
    total = sum(h.value_inr for h in holdings)
    s.profile.existing_holdings = holdings
    if s.profile.existing_corpus_inr <= 0:
        s.profile.existing_corpus_inr = total
    await request.app.state.session_store.save(s)
    set_cookie(response, s.id)
    return {
        "holdings": [h.model_dump() for h in holdings],
        "total_value_inr": total,
        "count": len(holdings),
    }


@router.post("/profile/cibil")
async def upload_cibil(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    password: str = Form(...),
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> dict:
    """Parse an uploaded CIBIL CIR PDF and attach credit_summary to the session.

    PDF body + password (PDF's user password — set when downloading the CIR).
    ``liabilities_inr`` on the profile is auto-filled when currently 0.
    Raw bytes live only in a tempfile that pdfminer reads + discards.
    """
    from subprime.data.cibil import CIBILParseError, parse_cibil

    s = await get_or_create(request, benji_session)
    pdf_bytes = await file.read()
    if len(pdf_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, "CIBIL PDF larger than 10 MB — refuse.")
    try:
        summary = parse_cibil(pdf_bytes, password.strip())
    except CIBILParseError as e:
        raise HTTPException(400, f"Couldn't parse CIBIL report: {e}")

    if s.profile is None:
        raise HTTPException(400, "Submit the profile form first, then upload a CIBIL report.")
    s.profile.credit_summary = summary
    if s.profile.liabilities_inr <= 0:
        s.profile.liabilities_inr = summary.total_outstanding_inr
    await request.app.state.session_store.save(s)
    set_cookie(response, s.id)
    return {
        "total_outstanding_inr": summary.total_outstanding_inr,
        "total_monthly_emi_inr": summary.total_monthly_emi_inr,
        "total_overdue_inr": summary.total_overdue_inr,
        "active_account_count": summary.active_account_count,
        "closed_account_count": summary.closed_account_count,
        "has_overdue": summary.has_overdue,
        "accounts": [a.model_dump() for a in summary.accounts],
    }


@router.post("/profile/documents")
async def upload_documents(
    request: Request,
    response: Response,
    files: list[UploadFile] = File(...),
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> dict:
    """Stage one or more PDFs for later extraction.

    Each file is inspected for encryption + classified if already unlocked.
    Returns the staged-document list; caller provides passwords for any
    entries with ``requires_password=True`` via /profile/documents/{id}/password.
    """
    from subprime.data.documents import list_docs, stage

    s = await get_or_create(request, benji_session)
    errors = []
    for f in files:
        try:
            pdf_bytes = await f.read()
            stage(s.id, f.filename or "upload.pdf", pdf_bytes)
        except ValueError as e:
            errors.append({"filename": f.filename, "error": str(e)})
    set_cookie(response, s.id)
    return {
        "documents": [d.to_public() for d in list_docs(s.id)],
        "errors": errors,
    }


@router.get("/profile/documents")
async def get_documents(
    request: Request,
    response: Response,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> dict:
    from subprime.data.documents import list_docs

    s = await get_or_create(request, benji_session)
    set_cookie(response, s.id)
    return {"documents": [d.to_public() for d in list_docs(s.id)]}


class _DocPassword(BaseModel):
    password: str


@router.post("/profile/documents/{doc_id}/password")
async def set_document_password(
    doc_id: str,
    body: _DocPassword,
    request: Request,
    response: Response,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> dict:
    from subprime.data.documents import apply_password

    s = await get_or_create(request, benji_session)
    try:
        doc = apply_password(s.id, doc_id, body.password)
    except KeyError:
        raise HTTPException(404, "Document not staged (may have expired).")
    except ValueError as e:
        raise HTTPException(400, str(e))
    set_cookie(response, s.id)
    return doc.to_public()


@router.delete("/profile/documents/{doc_id}")
async def remove_document(
    doc_id: str,
    request: Request,
    response: Response,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> dict:
    from subprime.data.documents import remove

    s = await get_or_create(request, benji_session)
    remove(s.id, doc_id)
    set_cookie(response, s.id)
    return {"ok": True}


@router.post("/profile/documents/extract")
async def extract_documents(
    request: Request,
    response: Response,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> dict:
    """Parse every verified staged doc, merge into the session profile.

    CAS → profile.existing_holdings (+ existing_corpus_inr fill)
    CIBIL → profile.credit_summary (+ liabilities_inr fill)
    On success, the staged bytes are purged.
    """
    from subprime.core.models import CreditSummary, Holding
    from subprime.data.documents import clear_session, extract_all

    s = await get_or_create(request, benji_session)
    if s.profile is None:
        raise HTTPException(400, "Submit the profile form first, then extract documents.")

    result = extract_all(s.id)
    holdings = [Holding(**h) for h in result["holdings"]]
    credit = CreditSummary(**result["credit_summary"]) if result["credit_summary"] else None

    if holdings:
        s.profile.existing_holdings = holdings
        total = sum(h.value_inr for h in holdings)
        if s.profile.existing_corpus_inr <= 0:
            s.profile.existing_corpus_inr = total
    if credit is not None:
        s.profile.credit_summary = credit
        if s.profile.liabilities_inr <= 0:
            s.profile.liabilities_inr = credit.total_outstanding_inr

    await request.app.state.session_store.save(s)
    clear_session(s.id)
    set_cookie(response, s.id)
    return {
        "holdings_count": len(holdings),
        "holdings_total_inr": sum(h.value_inr for h in holdings),
        "credit_summary": credit.model_dump() if credit else None,
        "skipped": result["skipped"],
    }


@router.post("/session/persona")
async def select_persona(
    body: PersonaSelectBody,
    request: Request,
    response: Response,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> SessionSummaryResponse:
    """Pick a preset persona from the research bank. Requires is_demo=True."""
    s = await get_or_create(request, benji_session)
    if not s.is_demo:
        raise HTTPException(403, "Persona bank is only available in demo mode.")
    try:
        profile = get_persona(body.persona_id)
    except (KeyError, ValueError):
        raise HTTPException(404, f"Persona '{body.persona_id}' not found")
    s.profile = profile
    if s.current_step < 3:
        s.current_step = 3
    await request.app.state.session_store.save(s)
    set_cookie(response, s.id)
    return SessionSummaryResponse.from_session(s)


@router.post("/session/profile")
async def submit_profile(
    body: ProfileBody,
    request: Request,
    response: Response,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> SessionSummaryResponse:
    """Save a custom-built InvestorProfile on the session."""
    s = await get_or_create(request, benji_session)
    profile = InvestorProfile(
        id="custom",
        name=body.name,
        age=body.age,
        risk_appetite=body.risk_appetite,
        investment_horizon_years=body.investment_horizon_years,
        monthly_investible_surplus_inr=body.monthly_sip_inr,
        existing_corpus_inr=body.existing_corpus_inr,
        liabilities_inr=0,
        financial_goals=body.financial_goals or ["Wealth Building"],
        life_stage=body.life_stage,
        tax_bracket=body.tax_bracket,
        preferences=body.preferences,
    )
    s.profile = profile
    if s.current_step < 3:
        s.current_step = 3
    await request.app.state.session_store.save(s)
    set_cookie(response, s.id)
    return SessionSummaryResponse.from_session(s)


@router.post("/session/otp/request")
async def otp_request(
    body: OTPRequestBody,
    request: Request,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> OTPSendResponse:
    """Generate an OTP for the given email and dispatch it via SMTP.

    If no DB pool is configured the endpoint returns ``sent=False`` — callers
    can still bypass with ``SUBPRIME_OTP_CHEAT`` on the verify endpoint.
    """
    pool = get_pool()
    if not pool:
        return OTPSendResponse(sent=False, message="Premium unavailable — no DB configured.")
    email = body.email.strip().lower()

    result = await create_otp(pool, email)
    if not result.get("success"):
        return OTPSendResponse(sent=False, message=result.get("reason", "Could not generate code."))

    # SMTP delivery is best-effort — log failures but still tell the client
    # the code was generated so they can try verifying.
    try:
        from apps.web.email import send_otp_email

        await send_otp_email(email, result["code"])
    except Exception:
        logger.exception("SMTP delivery failed for %s", email)

    return OTPSendResponse(sent=True, message=f"Code sent to {email}")


@router.post("/session/otp/verify")
async def otp_verify(
    body: OTPVerifyBody,
    request: Request,
    response: Response,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> OTPVerifyResponse:
    """Verify an OTP and unlock demo mode.

    Also accepts a ``SUBPRIME_OTP_CHEAT`` cheat code for testing.
    """
    cheat = os.environ.get("SUBPRIME_OTP_CHEAT", "").strip()
    is_cheat = bool(cheat) and body.code.strip() == cheat

    pool = get_pool()
    verified = is_cheat
    if not verified and pool:
        verified = await verify_otp(pool, body.email.strip().lower(), body.code.strip())

    if not verified:
        return OTPVerifyResponse(verified=False, is_demo=False, message="Invalid or expired code.")

    s = await get_or_create(request, benji_session)
    s.is_demo = True
    s.mode = "premium"
    s.email = body.email.strip().lower() or None
    await request.app.state.session_store.save(s)
    set_cookie(response, s.id)
    return OTPVerifyResponse(verified=True, is_demo=True)


@router.post("/session/reset")
async def reset(
    request: Request,
    response: Response,
) -> SessionSummaryResponse:
    """Start a fresh session — old cookie is overwritten."""
    s = Session()
    await request.app.state.session_store.save(s)
    set_cookie(response, s.id)
    return SessionSummaryResponse.from_session(s)
