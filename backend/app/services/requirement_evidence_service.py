from typing import List, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tender import TenderRequirement, TenderRequirementEvidence

# Controlled source-grounded evidence mapping rules: (keywords, evidence_type, doc_name, purpose)
EVIDENCE_RULES: List[Tuple[Tuple[str, ...], str, str, str]] = [
    (
        ("audited balance sheet", "audited financial", "balance sheet", "profit and loss"),
        "AUDITED_FINANCIAL_STATEMENTS",
        "Audited Financial Statements",
        "Verify financial capacity and annual turnover from audited statements.",
    ),
    (
        ("turnover certificate", "ca certificate", "chartered accountant", "annual turnover"),
        "TURNOVER_CERTIFICATE",
        "CA-Certified Annual Turnover Certificate",
        "Verify average annual turnover threshold compliance.",
    ),
    (
        ("gst", "gstin"),
        "GST_CERTIFICATE",
        "GST Registration Certificate",
        "Verify bidder GST registration and tax standing.",
    ),
    (
        ("pan ", "pan card", "permanent account number"),
        "PAN",
        "PAN Card Copy",
        "Verify bidder income tax PAN identity.",
    ),
    (
        ("work order", "purchase order", "similar contract"),
        "WORK_ORDER",
        "Prior Work / Purchase Order Copies",
        "Demonstrate prior execution of similar contracts.",
    ),
    (
        ("completion certificate", "performance certificate"),
        "COMPLETION_CERTIFICATE",
        "Client Completion / Performance Certificate",
        "Verify satisfactory completion of referenced past projects.",
    ),
    (
        ("iso 9001", "iso 27001", "iso "),
        "ISO_CERTIFICATE",
        "Valid ISO Certification",
        "Verify active quality/security ISO certification.",
    ),
    (
        ("bis ", "bis certificate"),
        "BIS_CERTIFICATE",
        "BIS Compliance Certificate",
        "Verify mandatory BIS product certification.",
    ),
    (
        ("udyam", "msme", "nsic"),
        "MSME_OR_UDYAM_CERTIFICATE",
        "Udyam / MSME Registration Certificate",
        "Verify MSME/Udyam eligibility or exemption claim.",
    ),
    (
        ("emd", "earnest money"),
        "EMD_PROOF",
        "Earnest Money Deposit (EMD) Receipt / Instrument",
        "Verify bid security deposit or exemption proof.",
    ),
    (
        ("performance bank guarantee", "pbg", "bank guarantee"),
        "BANK_GUARANTEE",
        "Performance Bank Guarantee (PBG)",
        "Verify performance security commitment.",
    ),
    (
        ("datasheet", "data sheet", "technical specification", "brochure"),
        "TECHNICAL_DATASHEET",
        "OEM Technical Datasheet / Compliance Sheet",
        "Verify proposed product meets technical specifications.",
    ),
    (
        ("manufacturer authorization", "maf", "oem authorization"),
        "OEM_AUTHORIZATION",
        "Manufacturer Authorization Form (MAF)",
        "Verify OEM authorization for the specific tender.",
    ),
    (
        ("non-blacklisting", "non-debarment", "self-declaration", "declaration", "make in india", "local content"),
        "SELF_DECLARATION",
        "Signed Bidder Self-Declaration / Undertaking",
        "Confirm statutory/compliance declarations.",
    ),
]


class TenderRequirementEvidenceService:
    """Deterministic, source-grounded expected evidence mapper (never auto-confirms)."""

    async def generate_for_requirement(
        self,
        db: AsyncSession,
        tender_id: UUID,
        requirement_id: UUID,
    ) -> List[TenderRequirementEvidence]:
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

        source_passage = (req.source_text or "").strip()
        if not source_passage:
            return []

        search_blob = " ".join(
            filter(
                None,
                [
                    source_passage,
                    req.expected_document_or_evidence,
                    req.normalized_statement,
                ],
            )
        ).lower()

        existing = (
            await db.execute(
                select(TenderRequirementEvidence).where(
                    TenderRequirementEvidence.requirement_id == req.id,
                    TenderRequirementEvidence.tender_id == tender_id,
                )
            )
        ).scalars().all()
        existing_by_type = {e.evidence_type: e for e in existing}

        is_mandatory = req.mandatory_status == "MANDATORY"
        needs_review = (not req.source_quote_verified) or (req.mandatory_status == "UNCLEAR")
        base_status = "NEEDS_REVIEW" if needs_review else "SUGGESTED"
        base_conf = 0.45 if needs_review else 0.85

        results: List[TenderRequirementEvidence] = []
        matched_types: set[str] = set()

        for keywords, ev_type, doc_name, purpose in EVIDENCE_RULES:
            if any(kw in search_blob for kw in keywords):
                matched_types.add(ev_type)
                ex = existing_by_type.get(ev_type)
                if ex:
                    # Preserve human CONFIRMED or REJECTED mappings
                    if ex.mapping_status in ("CONFIRMED", "REJECTED"):
                        results.append(ex)
                        continue
                    ex.expected_document_name = doc_name
                    ex.evidence_purpose = purpose
                    ex.is_mandatory = is_mandatory
                    ex.source_passage = source_passage
                    ex.confidence = base_conf
                    ex.mapping_status = base_status
                    results.append(ex)
                else:
                    rec = TenderRequirementEvidence(
                        tender_id=tender_id,
                        requirement_id=req.id,
                        evidence_type=ev_type,
                        expected_document_name=doc_name,
                        evidence_purpose=purpose,
                        is_mandatory=is_mandatory,
                        source_passage=source_passage,
                        mapping_method="DETERMINISTIC_RULE",
                        confidence=base_conf,
                        mapping_status=base_status,
                    )
                    db.add(rec)
                    existing_by_type[ev_type] = rec
                    results.append(rec)

        # If requirement explicitly names an expected_document_or_evidence not covered above
        if not matched_types and req.expected_document_or_evidence:
            ex_other = existing_by_type.get("OTHER")
            if ex_other:
                results.append(ex_other)
            else:
                rec = TenderRequirementEvidence(
                    tender_id=tender_id,
                    requirement_id=req.id,
                    evidence_type="OTHER",
                    expected_document_name=req.expected_document_or_evidence[:255],
                    evidence_purpose=req.explanatory_interpretation or "Supporting document referenced by tender.",
                    is_mandatory=is_mandatory,
                    source_passage=source_passage,
                    mapping_method="DETERMINISTIC_RULE",
                    confidence=0.45 if needs_review else 0.7,
                    mapping_status=base_status,
                )
                db.add(rec)
                results.append(rec)

        await db.flush()
        return results
