import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tender import (
    TenderDocument,
    TenderDocumentPage,
    TenderRequirement,
    TenderRequirementSource,
)
from app.services.clause_extractor import _tokenize_text, verify_source_text_presence


def _normalize_ocr_text(text: str) -> str:
    """Normalize line-break hyphenation, whitespace, and common OCR punctuation noise for comparison."""
    cleaned = re.sub(r"-\s*\n\s*", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.replace("—", "-").replace("–", "-").replace("’", "'").replace("“", '"').replace("”", '"')
    return cleaned.strip()


def verify_quote_against_pages(
    source_text: str,
    expected_page: int,
    pages_payload: List[Dict[str, Any]],
    recorded_sha256: Optional[str] = None,
    current_sha256: Optional[str] = None,
) -> Tuple[str, Optional[int], str]:
    """Deterministic multi-tier provenance verification without altering original source_text."""
    if recorded_sha256 and current_sha256 and recorded_sha256 != current_sha256:
        return "SOURCE_CHANGED", None, "Source document SHA-256 changed after requirement extraction."

    if not pages_payload:
        return "SOURCE_NOT_FOUND", None, "No persisted source pages exist for the referenced document."

    raw_quote = (source_text or "").strip()
    if not raw_quote:
        return "UNVERIFIED", None, "Requirement source quotation is empty."

    page_map = {int(p["page_number"]): p for p in pages_payload}
    target_page_obj = page_map.get(int(expected_page))

    # Tier 1: Exact contiguous token sequence on the attributed page
    if target_page_obj:
        ok, matched_page, _ = verify_source_text_presence(raw_quote, [target_page_obj])
        if ok:
            return "VERIFIED", matched_page, "Exact verbatim quotation verified on attributed page."

    # Tier 2: OCR/hyphenation/whitespace-normalized match on attributed page
    norm_quote_tokens = _tokenize_text(_normalize_ocr_text(raw_quote))
    if target_page_obj and len(norm_quote_tokens) >= 3:
        norm_page_tokens = _tokenize_text(_normalize_ocr_text(target_page_obj["text"]))
        k = len(norm_quote_tokens)
        for i in range(len(norm_page_tokens) - k + 1):
            if norm_page_tokens[i : i + k] == norm_quote_tokens:
                return (
                    "PARTIALLY_VERIFIED",
                    int(expected_page),
                    "Quotation matched on attributed page after whitespace/hyphenation normalization.",
                )

    # Tier 3: Exact or normalized match on another page of the same document (wrong page attribution)
    ok_other, matched_other, _ = verify_source_text_presence(raw_quote, pages_payload)
    if ok_other:
        return (
            "PARTIALLY_VERIFIED",
            matched_other,
            f"Quotation found on page {matched_other} instead of attributed page {expected_page}; needs review.",
        )

    # Tier 4: High token containment (>= 80%) on attributed page (partial OCR artifact tolerance)
    if target_page_obj and len(norm_quote_tokens) >= 4:
        q_set = set(norm_quote_tokens)
        p_set = set(_tokenize_text(_normalize_ocr_text(target_page_obj["text"])))
        overlap = len(q_set & p_set) / len(q_set)
        if overlap >= 0.8:
            return (
                "PARTIALLY_VERIFIED",
                int(expected_page),
                "High token overlap on attributed page with minor OCR/formatting differences.",
            )

    if not target_page_obj:
        return (
            "SOURCE_NOT_FOUND",
            None,
            f"Attributed page {expected_page} was not found in persisted document pages.",
        )

    return "UNVERIFIED", None, "Quotation could not be verified against persisted document pages."


class TenderRequirementProvenanceService:
    """Traces and verifies TenderRequirement provenance against persisted TenderDocumentPage rows."""

    async def verify_and_get_provenance(
        self,
        db: AsyncSession,
        tender_id: UUID,
        requirement_id: UUID,
        persist_status: bool = True,
    ) -> Dict[str, Any]:
        req = (
            await db.execute(
                select(TenderRequirement).where(
                    TenderRequirement.id == requirement_id,
                    TenderRequirement.tender_id == tender_id,
                )
            )
        ).scalar_one_or_none()
        if not req:
            raise ValueError("Tender requirement not found.")

        doc = (
            await db.execute(
                select(TenderDocument).where(TenderDocument.id == req.source_document_id)
            )
        ).scalar_one_or_none()
        page_rows = (
            await db.execute(
                select(TenderDocumentPage)
                .where(TenderDocumentPage.tender_document_id == req.source_document_id)
                .order_by(TenderDocumentPage.page_number.asc())
            )
        ).scalars().all()
        pages_payload = [
            {"page_number": p.page_number, "text": p.extracted_text}
            for p in page_rows
        ]

        status_val, matched_page, detail = verify_quote_against_pages(
            source_text=req.source_text,
            expected_page=req.source_page_number,
            pages_payload=pages_payload,
            recorded_sha256=req.source_document_sha256,
            current_sha256=doc.sha256_hash if doc else None,
        )

        if persist_status and req.provenance_status != status_val:
            req.provenance_status = status_val
            if doc and not req.source_document_sha256:
                req.source_document_sha256 = doc.sha256_hash
            await db.flush()

        extra_sources = (
            await db.execute(
                select(TenderRequirementSource)
                .where(
                    TenderRequirementSource.requirement_id == req.id,
                    TenderRequirementSource.tender_id == tender_id,
                )
                .order_by(TenderRequirementSource.created_at.asc())
            )
        ).scalars().all()

        return {
            "requirement": req,
            "source_document": doc,
            "verification_status": status_val,
            "matched_page_number": matched_page,
            "verification_detail": detail,
            "supporting_sources": extra_sources,
        }

    async def add_supporting_source(
        self,
        db: AsyncSession,
        tender_id: UUID,
        requirement_id: UUID,
        source_document_id: UUID,
        source_page_number: int,
        source_text: str,
        source_role: str = "ADDITIONAL_SUPPORTING",
        source_section: Optional[str] = None,
    ) -> TenderRequirementSource:
        doc = (
            await db.execute(
                select(TenderDocument).where(
                    TenderDocument.id == source_document_id,
                    TenderDocument.tender_id == tender_id,
                )
            )
        ).scalar_one_or_none()
        if not doc:
            raise ValueError("Supporting source document not found for tender.")

        page_rows = (
            await db.execute(
                select(TenderDocumentPage)
                .where(TenderDocumentPage.tender_document_id == source_document_id)
                .order_by(TenderDocumentPage.page_number.asc())
            )
        ).scalars().all()
        pages_payload = [{"page_number": p.page_number, "text": p.extracted_text} for p in page_rows]
        v_status, _, _ = verify_quote_against_pages(
            source_text=source_text,
            expected_page=source_page_number,
            pages_payload=pages_payload,
        )

        rec = TenderRequirementSource(
            tender_id=tender_id,
            requirement_id=requirement_id,
            source_document_id=source_document_id,
            source_role=source_role,
            source_page_number=source_page_number,
            source_section=source_section,
            source_text=source_text.strip(),
            verification_status=v_status,
            source_document_sha256=doc.sha256_hash,
        )
        db.add(rec)
        await db.flush()
        return rec
