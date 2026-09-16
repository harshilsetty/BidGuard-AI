"""REST API router for Phase 8.4 Verification Intelligence & Officer Risk View.

Endpoints:
- GET /tenders/{tender_id}/bidders/{bidder_id}/verification-summary
- GET /tenders/{tender_id}/bidders/{bidder_id}/verification-history
- GET /tenders/{tender_id}/review-queue

Enforces tender and bidder membership isolation. Mismatch returns HTTP 404.
"""

import logging
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.verification_intelligence import (
    OfficerBidderVerificationSummary,
    OfficerReviewQueueResponse,
    VerificationHistoryResponse,
)
from app.services.verification_intelligence_service import VerificationIntelligenceService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Verification Intelligence & Officer Risk"])


@router.get(
    "/tenders/{tender_id}/bidders/{bidder_id}/verification-summary",
    response_model=OfficerBidderVerificationSummary,
    summary="Consolidated officer verification intelligence summary",
    description=(
        "Returns consolidated risk state, base 100-point compliance score, debarment facts, "
        "status across all 11 statutory sources, contradictions, identity conflicts, "
        "and structured provenance-traceable risk reasons for officer review."
    ),
)
async def get_bidder_verification_summary(
    tender_id: UUID,
    bidder_id: UUID,
    as_of_date: Optional[date] = Query(
        None,
        description="Optional evaluation reference date. If omitted, retains existing UNKNOWN_PERIOD semantics without date.today() fallback.",
    ),
    db: AsyncSession = Depends(get_db),
) -> OfficerBidderVerificationSummary:
    """Retrieve consolidated officer risk summary for a bidder under a tender."""
    try:
        return await VerificationIntelligenceService.get_bidder_verification_summary(
            tender_id=tender_id,
            bidder_id=bidder_id,
            db=db,
            as_of_date=as_of_date,
        )
    except ValueError as e:
        logger.warning(f"Verification summary 404: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to generate verification summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification intelligence aggregation failed: {str(e)}",
        )


@router.get(
    "/tenders/{tender_id}/bidders/{bidder_id}/verification-history",
    response_model=VerificationHistoryResponse,
    summary="Retrieve append-only statutory verification history",
    description=(
        "Fetches the complete chronological history of all statutory verification executions "
        "for a specific bidder under a tender, preserving every attempt and clearly distinguishing "
        "the latest execution per authority from prior historical runs."
    ),
)
async def get_bidder_verification_history(
    tender_id: UUID,
    bidder_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> VerificationHistoryResponse:
    """Retrieve complete append-only verification history for a bidder."""
    try:
        return await VerificationIntelligenceService.get_bidder_verification_history(
            tender_id=tender_id,
            bidder_id=bidder_id,
            db=db,
        )
    except ValueError as e:
        logger.warning(f"Verification history 404: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to fetch verification history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification history retrieval failed: {str(e)}",
        )


@router.get(
    "/tenders/{tender_id}/review-queue",
    response_model=OfficerReviewQueueResponse,
    summary="Retrieve officer human review queue",
    description=(
        "Returns deterministically ordered list of all bidders under the tender that require "
        "officer review due to active debarments, major contradictions, identity discrepancies, "
        "critical technical source failures, or missing documentation."
    ),
)
async def get_tender_review_queue(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> OfficerReviewQueueResponse:
    """Retrieve tender review queue of bidders requiring officer action."""
    try:
        return await VerificationIntelligenceService.get_tender_review_queue(
            tender_id=tender_id,
            db=db,
        )
    except ValueError as e:
        logger.warning(f"Review queue 404: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to generate review queue: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Review queue evaluation failed: {str(e)}",
        )
