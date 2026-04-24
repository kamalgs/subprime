"""Supporting document staging + classification.

User uploads one or more PDFs (CAS, CIBIL, ...). We:
  1. Stage the bytes in a short-TTL in-memory store keyed by session
  2. Detect whether each PDF is password-protected
  3. Accept a password per doc and verify it unlocks the PDF
  4. Classify the unlocked doc (CAS vs CIBIL vs unknown) from its first page
  5. On "extract all", route each doc to its parser and return a
     consolidated result

PDF bytes never touch disk beyond a private tempfile read-once during
parsing. The in-memory store auto-purges entries older than _TTL_SECONDS.
"""

from __future__ import annotations

import io
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# Document type classifier returns
DocType = Literal["cas", "cibil", "ais", "unknown"]

_TTL_SECONDS = 30 * 60  # 30 min
_MAX_DOCS_PER_SESSION = 6
_MAX_BYTES = 10 * 1024 * 1024


@dataclass
class StagedDocument:
    doc_id: str
    filename: str
    size_bytes: int
    staged_at: float
    pdf_bytes: bytes = field(repr=False)
    requires_password: bool = False
    password: Optional[str] = field(default=None, repr=False)
    verified: bool = False
    detected_type: DocType = "unknown"

    def to_public(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "requires_password": self.requires_password,
            "verified": self.verified,
            "detected_type": self.detected_type,
        }


# session_id → { doc_id → StagedDocument }
_store: dict[str, dict[str, StagedDocument]] = {}


def _gc() -> None:
    """Evict stage entries older than _TTL_SECONDS."""
    cutoff = time.monotonic() - _TTL_SECONDS
    for sid, docs in list(_store.items()):
        for did, d in list(docs.items()):
            if d.staged_at < cutoff:
                del docs[did]
        if not docs:
            del _store[sid]


# ── PDF inspection ─────────────────────────────────────────────────────


def _is_encrypted(pdf_bytes: bytes) -> bool:
    """True when the PDF requires a password to read."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        return bool(reader.is_encrypted)
    except Exception:
        # Corrupt PDF: treat as not-encrypted so classifier can produce
        # a clearer "unrecognised" error later.
        return False


def verify_password(pdf_bytes: bytes, password: str) -> bool:
    """True when *password* successfully decrypts *pdf_bytes*."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        if not reader.is_encrypted:
            return True
        return bool(reader.decrypt(password))
    except Exception:
        return False


def _first_page_text(pdf_bytes: bytes, password: str | None) -> str:
    """Extract text from the first couple of pages for classification."""
    import tempfile
    from pathlib import Path

    try:
        from pdfminer.high_level import extract_text

        with tempfile.NamedTemporaryFile(prefix="subprime-", suffix=".pdf", delete=True) as tmp:
            tmp.write(pdf_bytes)
            tmp.flush()
            return extract_text(str(Path(tmp.name)), password=password or "", maxpages=2)
    except Exception:
        logger.exception("pdfminer extract failed during classification")
        return ""


def classify(pdf_bytes: bytes, password: str | None) -> DocType:
    """Inspect the unlocked PDF and return its document kind.

    Heuristic: match unique header strings from the respective bureau /
    registrar layouts. Cheap to add a third kind later — just extend the
    if-chain and write a parser module.
    """
    text = _first_page_text(pdf_bytes, password).upper()
    if not text:
        return "unknown"
    if "CIBIL TRANSUNION SCORE" in text or "TRANSUNION CIBIL" in text:
        return "cibil"
    if "ANNUAL INFORMATION STATEMENT" in text:
        return "ais"
    if (
        "CONSOLIDATED ACCOUNT STATEMENT" in text
        or "CONSOLIDATED ACCOUNT SUMMARY" in text
        or ("CAMS" in text and "MUTUAL FUND" in text)
        or ("KFINTECH" in text and "FOLIO" in text)
    ):
        return "cas"
    return "unknown"


# ── Staging lifecycle ─────────────────────────────────────────────────


def stage(session_id: str, filename: str, pdf_bytes: bytes) -> StagedDocument:
    """Register an uploaded PDF. Probes for encryption + runs classifier.

    Raises ValueError when the stage limit or size cap is exceeded.
    """
    _gc()
    if len(pdf_bytes) > _MAX_BYTES:
        raise ValueError(f"{filename}: larger than {_MAX_BYTES // (1024 * 1024)} MB")
    session_docs = _store.setdefault(session_id, {})
    if len(session_docs) >= _MAX_DOCS_PER_SESSION:
        raise ValueError(f"Max {_MAX_DOCS_PER_SESSION} documents per session")

    encrypted = _is_encrypted(pdf_bytes)
    detected: DocType = "unknown"
    verified = False
    if not encrypted:
        detected = classify(pdf_bytes, password=None)
        verified = True

    doc = StagedDocument(
        doc_id=uuid.uuid4().hex[:12],
        filename=filename,
        size_bytes=len(pdf_bytes),
        staged_at=time.monotonic(),
        pdf_bytes=pdf_bytes,
        requires_password=encrypted,
        verified=verified,
        detected_type=detected,
    )
    session_docs[doc.doc_id] = doc
    return doc


def apply_password(session_id: str, doc_id: str, password: str) -> StagedDocument:
    """Verify *password* against the staged PDF; update detected_type on success."""
    _gc()
    doc = _get_or_raise(session_id, doc_id)
    if not doc.requires_password:
        doc.verified = True
        return doc
    if not verify_password(doc.pdf_bytes, password):
        raise ValueError("Incorrect password")
    doc.password = password
    doc.verified = True
    doc.detected_type = classify(doc.pdf_bytes, password=password)
    return doc


def remove(session_id: str, doc_id: str) -> None:
    _gc()
    docs = _store.get(session_id) or {}
    docs.pop(doc_id, None)


def list_docs(session_id: str) -> list[StagedDocument]:
    _gc()
    return list((_store.get(session_id) or {}).values())


def extract_all(session_id: str) -> dict:
    """Run each verified doc through its parser; return consolidated result.

    - CAS docs → list[Holding]
    - CIBIL docs → CreditSummary (most recent one wins if multiple)
    - Unknown / unverified docs skipped but listed in ``skipped``
    """
    _gc()
    docs = list_docs(session_id)
    holdings: list = []
    credit_summary = None
    ais_summary = None
    skipped: list[dict] = []

    for d in docs:
        if not d.verified:
            skipped.append({"doc_id": d.doc_id, "filename": d.filename, "reason": "unverified"})
            continue
        try:
            if d.detected_type == "cas":
                from subprime.data.cas import parse_cas

                holdings.extend(parse_cas(d.pdf_bytes, d.password or ""))
            elif d.detected_type == "cibil":
                from subprime.data.cibil import parse_cibil

                credit_summary = parse_cibil(d.pdf_bytes, d.password or "")
            elif d.detected_type == "ais":
                from subprime.data.ais import parse_ais

                ais_summary = parse_ais(d.pdf_bytes, d.password or "")
            else:
                skipped.append(
                    {"doc_id": d.doc_id, "filename": d.filename, "reason": "unknown-type"}
                )
        except Exception as e:
            # Don't log filename — user uploads are routinely named
            # things like "CAS_<PAN>_.pdf" or the user's full name.
            logger.exception("extract failed for doc_id=%s type=%s", d.doc_id, d.detected_type)
            skipped.append({"doc_id": d.doc_id, "filename": d.filename, "reason": str(e)[:200]})

    return {
        "holdings": [h.model_dump() for h in holdings],
        "credit_summary": credit_summary.model_dump() if credit_summary else None,
        "ais_summary": ais_summary.model_dump() if ais_summary else None,
        "skipped": skipped,
    }


def clear_session(session_id: str) -> None:
    """Drop all staged bytes for a session — call on extract success + session reset."""
    _store.pop(session_id, None)


def _get_or_raise(session_id: str, doc_id: str) -> StagedDocument:
    docs = _store.get(session_id) or {}
    if doc_id not in docs:
        raise KeyError(doc_id)
    return docs[doc_id]
