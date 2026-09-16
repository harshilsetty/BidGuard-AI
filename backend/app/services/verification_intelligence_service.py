"""Verification Intelligence Service.

Phase 8.4 — SIH26100 Verification Intelligence & Officer Risk View.
Aggregates statutory verification facts, temporal provenance, cross-source contradictions,
debarment state, and compliance evaluations into deterministic, officer-facing intelligence.

Strict Architectural Protections:
1. Phase 6.4 100-Point Score Formula is 100% UNCHANGED.
2. Debarment is orthogonal to the 100-point score (elevates risk to HIGH, score untouched).
3. Technical source failure (UNAVAILABLE, TIMEOUT, AUTH_FAILURE, FAILED) != bidder non-compliance.
4. Missing as_of_date remains UNKNOWN_PERIOD / UNVERIFIED without date.today() fallback.
5. Decision support only (no automatic disqualification or winner selection).
6. Exactly 11 statutory/mock sources.
7. Append-only verification history.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bidder import Bidder
from app.models.clause import TenderClause
from app.models.evaluation import ComplianceEvaluation
from app.models.statutory import StatutoryVerificationRecord
from app.models.tender import Tender
from app.schemas.cross_source_verification import CrossSourceStatus
from app.schemas.evaluation import ComplianceStatus
from app.schemas.scoring import RiskLevel, ScoreBreakdown
from app.schemas.statutory_verification import (
    DebarmentTemporalStatus,
    SourceConnectionStatus,
    SourceMode,
    SourceVerificationStatus,
    StatutoryAuthority,
)
from app.schemas.verification_intelligence import (
    DebarmentStateSummary,
    OFFICER_INTELLIGENCE_DISCLAIMER,
    OfficerBidderVerificationSummary,
    OfficerReviewQueueResponse,
    ReviewQueueItem,
    RiskReasonCode,
    RiskReasonItem,
    RiskReasonSeverity,
    SourceStatusItem,
    VerificationHistoryItem,
    VerificationHistoryResponse,
)
from app.services.cross_source_verifier import CrossSourceVerifier
from app.services.evidence_fusion_service import EvidenceFusionService
from app.services.scoring_service import ScoringAndRankingService

logger = logging.getLogger(__name__)

# Canonical 11 Statutory Sources
LOCKED_11_STATUTORY_AUTHORITIES: List[StatutoryAuthority] = [
    StatutoryAuthority.GSTN,
    StatutoryAuthority.UDYAM,
    StatutoryAuthority.MCA,
    StatutoryAuthority.INCOME_TAX,
    StatutoryAuthority.MII,
    StatutoryAuthority.DEBARMENT,
    StatutoryAuthority.DPIIT,
    StatutoryAuthority.EPFO,
    StatutoryAuthority.ESIC,
    StatutoryAuthority.NSIC,
    StatutoryAuthority.DIGILOCKER,
]

AUTHORITY_DISPLAY_NAMES: Dict[str, str] = {
    StatutoryAuthority.GSTN.value: "Goods & Services Tax Network (GSTN)",
    StatutoryAuthority.UDYAM.value: "Udyam MSME Registration Portal",
    StatutoryAuthority.MCA.value: "Ministry of Corporate Affairs (MCA)",
    StatutoryAuthority.INCOME_TAX.value: "Income Tax Department (CBDT)",
    StatutoryAuthority.MII.value: "Make in India (DPIIT Local Content)",
    StatutoryAuthority.DEBARMENT.value: "CPPP Central Debarment Register",
    StatutoryAuthority.DPIIT.value: "DPIIT / Startup India Recognition",
    StatutoryAuthority.EPFO.value: "Employees' Provident Fund Organisation (EPFO)",
    StatutoryAuthority.ESIC.value: "Employees' State Insurance Corporation (ESIC)",
    StatutoryAuthority.NSIC.value: "National Small Industries Corporation (NSIC)",
    StatutoryAuthority.DIGILOCKER.value: "DigiLocker Document Verification",
}


class VerificationIntelligenceService:
    """Read and aggregation service for officer verification intelligence and review queue."""

    @staticmethod
    async def get_bidder_verification_summary(
        tender_id: UUID,
        bidder_id: UUID,
        db: AsyncSession,
        as_of_date: Optional[date] = None,
    ) -> OfficerBidderVerificationSummary:
        """Construct consolidated officer verification intelligence summary.
        
        Aggregates statutory source health, cross-source contradictions, debarment facts,
        and evaluation completeness into explainable, structured risk reasons.
        Does NOT alter 100-point score formula or automatically disqualify bidders.
        """
        # 1. Enforce Tender & Bidder membership isolation
        tender_stmt = select(Tender).where(Tender.id == tender_id)
        tender = (await db.execute(tender_stmt)).scalar_one_or_none()
        if not tender:
            raise ValueError(f"Tender {tender_id} not found")

        bidder_stmt = select(Bidder).where(Bidder.id == bidder_id, Bidder.tender_id == tender_id)
        bidder = (await db.execute(bidder_stmt)).scalar_one_or_none()
        if not bidder:
            raise ValueError(f"Bidder {bidder_id} not found for tender {tender_id}")

        # 2. Query historical statutory records for this (tender_id, bidder_id)
        # Explicit stable ordering: retrieved_at DESC, created_at DESC, id DESC
        stat_stmt = (
            select(StatutoryVerificationRecord)
            .where(
                StatutoryVerificationRecord.tender_id == tender_id,
                StatutoryVerificationRecord.bidder_id == bidder_id,
            )
            .order_by(
                desc(StatutoryVerificationRecord.retrieved_at),
                desc(StatutoryVerificationRecord.created_at),
                desc(StatutoryVerificationRecord.id),
            )
        )
        stat_records = (await db.execute(stat_stmt)).scalars().all()

        # Group records by authority to separate latest attempt vs previous successful result
        records_by_authority: Dict[str, List[StatutoryVerificationRecord]] = {}
        for rec in stat_records:
            auth_val = rec.authority.upper()
            records_by_authority.setdefault(auth_val, []).append(rec)

        # 3. Build SourceStatusItem for all 11 authorities
        source_statuses: Dict[str, SourceStatusItem] = {}
        technical_source_failures: List[str] = []
        identity_conflicts: List[str] = []
        structured_reasons: List[RiskReasonItem] = []

        is_debarred_active = False
        debarment_summary = DebarmentStateSummary(
            is_debarred=False,
            temporal_status=SourceVerificationStatus.NOT_FOUND.value,
            order_number=None,
            authority=None,
            start_date=None,
            end_date=None,
            as_of_date=as_of_date,
            reason=None,
            verification_id=None,
            provenance_note="",
        )

        for auth_enum in LOCKED_11_STATUTORY_AUTHORITIES:
            auth_key = auth_enum.value
            records = records_by_authority.get(auth_key, [])

            if not records:
                # No execution recorded yet for this authority
                source_statuses[auth_key] = SourceStatusItem(
                    authority=auth_key,
                    source_name=AUTHORITY_DISPLAY_NAMES.get(auth_key, auth_key),
                    connection_status=SourceConnectionStatus.SUCCESS.value,
                    verification_status=SourceVerificationStatus.UNVERIFIED.value,
                    is_technical_failure=False,
                    is_business_not_found=False,
                    retrieved_at=None,
                    as_of_date=as_of_date,
                    query_identifier=None,
                    identifier_type=None,
                    validity_start=None,
                    validity_end=None,
                    provenance_note="Awaiting statutory verification execution",
                    verification_id=None,
                    error_message=None,
                    is_mock=True,
                    previous_successful_result=None,
                )
                continue

            latest_rec = records[0]
            conn_status = latest_rec.connection_status
            verif_status = latest_rec.verification_status

            # Technical failure classifications
            is_tech_failure = (
                conn_status in [
                    SourceConnectionStatus.TIMEOUT.value,
                    SourceConnectionStatus.UNAVAILABLE.value,
                    SourceConnectionStatus.AUTH_FAILURE.value,
                    SourceConnectionStatus.ERROR.value,
                    SourceConnectionStatus.RATE_LIMITED.value,
                ]
                or verif_status == SourceVerificationStatus.FAILED.value
            )

            # Business NOT_FOUND: transport succeeded, but entity absent in registry
            is_biz_not_found = (
                conn_status == SourceConnectionStatus.SUCCESS.value
                and verif_status == SourceVerificationStatus.NOT_FOUND.value
            )

            # Check if there was a previous successful result when latest is technical failure
            previous_successful = None
            if is_tech_failure and len(records) > 1:
                for prev in records[1:]:
                    if (
                        prev.connection_status == SourceConnectionStatus.SUCCESS.value
                        and prev.verification_status != SourceVerificationStatus.FAILED.value
                    ):
                        previous_successful = {
                            "verification_id": str(prev.verification_id),
                            "verification_status": prev.verification_status,
                            "retrieved_at": prev.retrieved_at.isoformat() if prev.retrieved_at else None,
                            "as_of_date": prev.as_of_date.isoformat() if prev.as_of_date else None,
                            "data_payload": prev.data_payload or {},
                        }
                        break

            # Extract validity dates if present in payload
            payload = latest_rec.data_payload or {}
            validity_start = payload.get("registration_date") or payload.get("issue_date") or payload.get("start_date") or payload.get("issued_at")
            validity_end = payload.get("expiry_date") or payload.get("end_date")

            source_statuses[auth_key] = SourceStatusItem(
                authority=auth_key,
                source_name=latest_rec.source_name or AUTHORITY_DISPLAY_NAMES.get(auth_key, auth_key),
                connection_status=conn_status,
                verification_status=verif_status,
                is_technical_failure=is_tech_failure,
                is_business_not_found=is_biz_not_found,
                retrieved_at=latest_rec.retrieved_at,
                as_of_date=latest_rec.as_of_date,
                query_identifier=latest_rec.query_identifier,
                identifier_type=latest_rec.identifier_type,
                validity_start=str(validity_start) if validity_start else None,
                validity_end=str(validity_end) if validity_end else None,
                provenance_note=latest_rec.provenance_note or "",
                verification_id=str(latest_rec.verification_id) if latest_rec.verification_id else None,
                error_message=latest_rec.error_message,
                is_mock=(latest_rec.mode == SourceMode.MOCK.value),
                previous_successful_result=previous_successful,
            )

            # Generate technical risk reasons
            if is_tech_failure:
                tech_msg = f"{latest_rec.source_name} ({conn_status}): {latest_rec.error_message or 'Service connection failed'}"
                technical_source_failures.append(tech_msg)

                code_map = {
                    SourceConnectionStatus.TIMEOUT.value: RiskReasonCode.SOURCE_TIMEOUT,
                    SourceConnectionStatus.UNAVAILABLE.value: RiskReasonCode.SOURCE_UNAVAILABLE,
                    SourceConnectionStatus.AUTH_FAILURE.value: RiskReasonCode.SOURCE_AUTH_FAILURE,
                }
                reason_code = code_map.get(conn_status, RiskReasonCode.SOURCE_FAILED)
                structured_reasons.append(
                    RiskReasonItem(
                        reason_code=reason_code,
                        severity=RiskReasonSeverity.REVIEW,
                        title=f"{latest_rec.source_name} Technical Failure ({conn_status})",
                        explanation=(
                            f"Statutory source connection failed with status '{conn_status}'. "
                            f"Per procurement rules, source failure does not imply bidder non-compliance. "
                            f"Officer review or verification retry is advised."
                        ),
                        source_type="STATUTORY",
                        source_name=latest_rec.source_name,
                        verification_id=str(latest_rec.verification_id),
                        requires_officer_review=True,
                    )
                )

            # Check for identity conflict or ambiguous match
            if payload.get("conflict_detected") or payload.get("is_ambiguous_match") or payload.get("officer_review_required"):
                conflict_msg = (
                    f"{latest_rec.source_name}: Identifier discrepancy detected. "
                    f"Queried '{latest_rec.query_identifier}' conflicts with authoritative bidder identity."
                )
                identity_conflicts.append(conflict_msg)
                structured_reasons.append(
                    RiskReasonItem(
                        reason_code=RiskReasonCode.IDENTITY_CONFLICT,
                        severity=RiskReasonSeverity.HIGH,
                        title=f"Identity Conflict: {latest_rec.source_name}",
                        explanation=conflict_msg,
                        source_type="STATUTORY",
                        source_name=latest_rec.source_name,
                        verification_id=str(latest_rec.verification_id),
                        requires_officer_review=True,
                    )
                )

            # Debarment inspection
            if auth_key == StatutoryAuthority.DEBARMENT.value:
                is_deb = payload.get("is_debarred_on_date", False)
                temp_status = payload.get("temporal_status", SourceVerificationStatus.NOT_FOUND.value)
                order_num = payload.get("order_number") or payload.get("debarment_order")
                deb_auth = payload.get("authority") or latest_rec.source_name
                deb_start = payload.get("start_date")
                deb_end = payload.get("end_date")
                deb_reason = payload.get("reason")

                if is_deb:
                    is_debarred_active = True

                debarment_summary = DebarmentStateSummary(
                    is_debarred=is_deb,
                    temporal_status=str(temp_status),
                    order_number=str(order_num) if order_num else None,
                    authority=str(deb_auth) if deb_auth else None,
                    start_date=str(deb_start) if deb_start else None,
                    end_date=str(deb_end) if deb_end else None,
                    as_of_date=latest_rec.as_of_date or as_of_date,
                    reason=str(deb_reason) if deb_reason else None,
                    verification_id=str(latest_rec.verification_id),
                    provenance_note=latest_rec.provenance_note or "",
                )

                if is_deb:
                    structured_reasons.append(
                        RiskReasonItem(
                            reason_code=RiskReasonCode.ACTIVE_DEBARMENT,
                            severity=RiskReasonSeverity.HIGH,
                            title="Active Debarment Detected",
                            explanation=(
                                f"Bidder has an active statutory debarment order ({order_num or 'Order On Record'}) "
                                f"effective from {deb_start} to {deb_end or 'Indefinite'}. "
                                f"Debarment reason: '{deb_reason or 'Non-compliance'}'. "
                                f"Elevates risk to HIGH; mandatory officer review required."
                            ),
                            source_type="DEBARMENT",
                            source_name=deb_auth or "CPPP Central Debarment Register",
                            verification_id=str(latest_rec.verification_id),
                            evidence_reference=str(order_num) if order_num else None,
                            requires_officer_review=True,
                        )
                    )

        # 4. Compute Base 100-point Score & Evaluations (Using authoritative services)
        c_stmt = select(TenderClause).where(TenderClause.tender_id == tender_id)
        clauses = (await db.execute(c_stmt)).scalars().all()
        clause_map = {c.clause_code: c.is_mandatory for c in clauses}
        clause_obj_map = {c.clause_code: c for c in clauses}

        eval_stmt = (
            select(ComplianceEvaluation)
            .where(ComplianceEvaluation.bidder_id == bidder_id)
            .options(selectinload(ComplianceEvaluation.clause))
        )
        eval_records = (await db.execute(eval_stmt)).scalars().all()
        evals_for_tender = [e for e in eval_records if e.clause and e.clause.tender_id == tender_id]

        profile = await EvidenceFusionService.fuse_bidder_evidence(
            bidder_id=bidder_id,
            db=db,
            tender_id=tender_id,
            company_name_override=bidder.company_name,
        )
        cross_report = CrossSourceVerifier.verify_profile(profile)

        # Calculate score using unmodified Phase 6.4 / 8.2 logic
        score_res = ScoringAndRankingService.calculate_bidder_score(
            bidder_id=bidder_id,
            company_name=bidder.company_name,
            evaluations=evals_for_tender,
            cross_source_report=cross_report,
            tender_id=tender_id,
            clause_mandatory_map=clause_map,
            is_debarred_on_date=is_debarred_active,
            debarment_details={
                "order_number": debarment_summary.order_number,
                "authority": debarment_summary.authority,
            } if is_debarred_active else None,
        )

        # 5. Extract Contradictions
        major_contradictions: List[str] = []
        if cross_report and cross_report.results:
            for r in cross_report.results:
                if r.status == CrossSourceStatus.INCONSISTENT:
                    contradiction_text = f"Field '{r.field_label}': {r.explanation}"
                    major_contradictions.append(contradiction_text)
                    structured_reasons.append(
                        RiskReasonItem(
                            reason_code=RiskReasonCode.MAJOR_CONTRADICTION,
                            severity=RiskReasonSeverity.HIGH,
                            title=f"Contradiction: {r.field_label}",
                            explanation=contradiction_text,
                            source_type="CROSS_SOURCE",
                            source_name="Cross-Source Verifier",
                            evidence_reference=r.field_name,
                            requires_officer_review=True,
                        )
                    )

        # Also inspect evaluations for detected contradictions
        for ev in evals_for_tender:
            if getattr(ev, "contradiction_detected", False):
                c_code = ev.clause.clause_code if ev.clause else "UNKNOWN"
                c_text = f"Clause [{c_code}]: {ev.contradiction_details or ev.reasoning or 'Contradiction detected'}"
                if c_text not in major_contradictions:
                    major_contradictions.append(c_text)
                    structured_reasons.append(
                        RiskReasonItem(
                            reason_code=RiskReasonCode.MAJOR_CONTRADICTION,
                            severity=RiskReasonSeverity.HIGH,
                            title=f"Contradiction: [{c_code}]",
                            explanation=c_text,
                            source_type="TENDER_CLAUSE",
                            source_name="Compliance Evaluation",
                            clause_code=c_code,
                            requires_officer_review=True,
                        )
                    )

        # 6. Extract Missing Evidence and OCR Quality
        missing_evidence_list: List[str] = []
        for ev in evals_for_tender:
            # Check completeness
            completeness = ScoringAndRankingService.evaluate_clause_evidence_completeness(ev)
            c_code = ev.clause.clause_code if ev.clause else "UNKNOWN"
            c_is_mand = ev.clause.is_mandatory if ev.clause else False

            if completeness == 0.0:
                missing_msg = f"Clause [{c_code}] {ev.clause.title if ev.clause else ''}: Evidence required but missing/unconfirmed."
                missing_evidence_list.append(missing_msg)
                structured_reasons.append(
                    RiskReasonItem(
                        reason_code=RiskReasonCode.INSUFFICIENT_EVIDENCE,
                        severity=RiskReasonSeverity.REVIEW,
                        title=f"Insufficient Evidence: [{c_code}]",
                        explanation=missing_msg,
                        source_type="TENDER_CLAUSE",
                        source_name="Compliance Evaluation",
                        clause_code=c_code,
                        requires_officer_review=True,
                    )
                )

            # Mandatory clause FAIL creates risk reason
            effective_status = ev.override_status or ev.status
            if c_is_mand and effective_status == ComplianceStatus.FAIL.value:
                structured_reasons.append(
                    RiskReasonItem(
                        reason_code=RiskReasonCode.MANDATORY_CLAUSE_FAIL,
                        severity=RiskReasonSeverity.HIGH,
                        title=f"Mandatory Clause Failed: [{c_code}]",
                        explanation=f"Bidder failed mandatory clause [{c_code}]: {ev.reasoning or 'Threshold not met'}.",
                        source_type="TENDER_CLAUSE",
                        source_name="Compliance Evaluation",
                        clause_code=c_code,
                        requires_officer_review=True,
                    )
                )

            # Check OCR confidence
            if ev.extraction_method == "OCR" and ev.ocr_confidence is not None:
                if float(ev.ocr_confidence) < 0.70:
                    ocr_msg = f"Clause [{c_code}]: OCR extraction confidence is low ({float(ev.ocr_confidence):.1%}). Human visual inspection advised."
                    structured_reasons.append(
                        RiskReasonItem(
                            reason_code=RiskReasonCode.OCR_LOW_CONFIDENCE,
                            severity=RiskReasonSeverity.REVIEW,
                            title=f"Low OCR Confidence: [{c_code}]",
                            explanation=ocr_msg,
                            source_type="OCR",
                            source_name="OCR Pipeline",
                            clause_code=c_code,
                            requires_officer_review=True,
                        )
                    )

        # 7. Check Temporal missing as_of_date
        if as_of_date is None:
            # Check if any statutory record evaluated without as_of_date
            any_none_as_of = any(r.as_of_date is None for r in stat_records)
            if any_none_as_of or stat_records:
                structured_reasons.append(
                    RiskReasonItem(
                        reason_code=RiskReasonCode.TEMPORAL_UNVERIFIED,
                        severity=RiskReasonSeverity.REVIEW,
                        title="Evaluation Date Unspecified (as_of_date is None)",
                        explanation="Statutory verification was queried without an evaluation reference date (as_of_date=None). Temporal validity remains unverified without assuming current date.",
                        source_type="STATUTORY",
                        source_name="Temporal Verifier",
                        requires_officer_review=True,
                    )
                )

        # 8. Determine Overall Risk & Officer Review Requirement
        # Debarment elevates overall risk to HIGH (Phase 8.2 locked invariant)
        overall_risk = RiskLevel.HIGH if is_debarred_active else score_res.risk_level

        # Officer review is required if any structured reason requires it
        officer_review_required = any(r.requires_officer_review for r in structured_reasons) or is_debarred_active

        return OfficerBidderVerificationSummary(
            bidder_id=str(bidder_id),
            tender_id=str(tender_id),
            company_name=bidder.company_name,
            overall_risk_state=overall_risk,
            base_compliance_score=score_res.overall_score,
            score_breakdown=score_res.breakdown,
            debarment_state=debarment_summary,
            source_statuses=source_statuses,
            major_contradictions=major_contradictions,
            identity_conflicts=identity_conflicts,
            missing_or_insufficient_evidence=missing_evidence_list,
            technical_source_failures=technical_source_failures,
            officer_review_required=officer_review_required,
            risk_reasons=structured_reasons,
            evaluated_at=datetime.now(timezone.utc),
            as_of_date=as_of_date,
            disclaimer=OFFICER_INTELLIGENCE_DISCLAIMER,
        )

    @staticmethod
    async def get_bidder_verification_history(
        tender_id: UUID,
        bidder_id: UUID,
        db: AsyncSession,
    ) -> VerificationHistoryResponse:
        """Retrieve append-only history of all statutory verification attempts for a bidder.
        
        Strictly preserves chronological attempts, separating latest attempt from past historical runs.
        Never updates or deletes past verification records.
        """
        # Validate tender and bidder membership
        b_stmt = select(Bidder).where(Bidder.id == bidder_id, Bidder.tender_id == tender_id)
        bidder = (await db.execute(b_stmt)).scalar_one_or_none()
        if not bidder:
            raise ValueError(f"Bidder {bidder_id} does not belong to tender {tender_id}")

        stmt = (
            select(StatutoryVerificationRecord)
            .where(
                StatutoryVerificationRecord.tender_id == tender_id,
                StatutoryVerificationRecord.bidder_id == bidder_id,
            )
            .order_by(
                desc(StatutoryVerificationRecord.retrieved_at),
                desc(StatutoryVerificationRecord.created_at),
                desc(StatutoryVerificationRecord.id),
            )
        )
        records = (await db.execute(stmt)).scalars().all()

        seen_authorities: Set[str] = set()
        history_items: List[VerificationHistoryItem] = []

        for r in records:
            auth_key = r.authority.upper()
            is_latest_for_auth = auth_key not in seen_authorities
            seen_authorities.add(auth_key)

            history_items.append(
                VerificationHistoryItem(
                    id=str(r.id),
                    verification_id=str(r.verification_id),
                    authority=r.authority,
                    source_name=r.source_name,
                    query_identifier=r.query_identifier,
                    identifier_type=r.identifier_type,
                    connection_status=r.connection_status,
                    verification_status=r.verification_status,
                    is_latest=is_latest_for_auth,
                    retrieved_at=r.retrieved_at,
                    as_of_date=r.as_of_date,
                    data_payload=r.data_payload or {},
                    confidence_score=float(r.confidence_score) if r.confidence_score is not None else 1.0,
                    provenance_note=r.provenance_note or "",
                    error_message=r.error_message,
                    execution_time_ms=float(r.execution_time_ms) if r.execution_time_ms is not None else 0.0,
                )
            )

        return VerificationHistoryResponse(
            bidder_id=str(bidder_id),
            tender_id=str(tender_id),
            total_attempts=len(history_items),
            history=history_items,
            disclaimer=OFFICER_INTELLIGENCE_DISCLAIMER,
        )

    @staticmethod
    async def get_tender_review_queue(
        tender_id: UUID,
        db: AsyncSession,
    ) -> OfficerReviewQueueResponse:
        """Construct deterministic officer review queue for all bidders under a tender.
        
        Collects bidders where officer review is triggered (active debarment, major contradictions,
        technical source failure, identity conflict, or insufficient evidence).
        Order deterministically: HIGH risk first, then trigger count DESC, then stable bidder_id ASC.
        """
        tender_stmt = select(Tender).where(Tender.id == tender_id)
        tender = (await db.execute(tender_stmt)).scalar_one_or_none()
        if not tender:
            raise ValueError(f"Tender {tender_id} not found")

        bidder_stmt = select(Bidder).where(Bidder.tender_id == tender_id).order_by(Bidder.created_at)
        bidders = (await db.execute(bidder_stmt)).scalars().all()

        queue_items: List[ReviewQueueItem] = []

        for bidder in bidders:
            try:
                summary = await VerificationIntelligenceService.get_bidder_verification_summary(
                    tender_id=tender_id,
                    bidder_id=bidder.id,
                    db=db,
                )
                if summary.officer_review_required:
                    triggers: List[str] = []
                    if summary.debarment_state.is_debarred:
                        triggers.append("Active Debarment Order")
                    if summary.major_contradictions:
                        triggers.append(f"{len(summary.major_contradictions)} Major Contradiction(s)")
                    if summary.identity_conflicts:
                        triggers.append("Identity Discrepancy")
                    if summary.technical_source_failures:
                        triggers.append(f"{len(summary.technical_source_failures)} Technical Failure(s)")
                    if summary.missing_or_insufficient_evidence:
                        triggers.append(f"{len(summary.missing_or_insufficient_evidence)} Missing Evidence Clause(s)")

                    queue_items.append(
                        ReviewQueueItem(
                            bidder_id=str(bidder.id),
                            tender_id=str(tender_id),
                            company_name=bidder.company_name,
                            overall_risk_state=summary.overall_risk_state,
                            compliance_score=summary.base_compliance_score,
                            review_triggers=triggers,
                            primary_risk_reasons=summary.risk_reasons[:5],
                            debarred=summary.debarment_state.is_debarred,
                            contradiction_count=len(summary.major_contradictions),
                            technical_failure_count=len(summary.technical_source_failures),
                            queued_at=datetime.now(timezone.utc),
                        )
                    )
            except Exception as e:
                logger.error(f"Error evaluating bidder {bidder.id} for review queue: {e}", exc_info=True)

        # Deterministic sorting:
        # 1. Overall risk: HIGH (0) -> MEDIUM (1) -> LOW (2)
        # 2. Number of review triggers descending
        # 3. Stable bidder_id string ascending
        severity_rank = {RiskLevel.HIGH: 0, RiskLevel.MEDIUM: 1, RiskLevel.LOW: 2}
        queue_items.sort(
            key=lambda item: (
                severity_rank.get(item.overall_risk_state, 3),
                0 if item.debarred else 1,
                -len(item.review_triggers),
                item.bidder_id,
            )
        )

        return OfficerReviewQueueResponse(
            tender_id=str(tender_id),
            total_queued=len(queue_items),
            items=queue_items,
            generated_at=datetime.now(timezone.utc),
            disclaimer=OFFICER_INTELLIGENCE_DISCLAIMER,
        )
