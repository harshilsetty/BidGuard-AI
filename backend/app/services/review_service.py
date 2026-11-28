from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.rbac import Role, RolePermission, UserRole
from app.models.tender import (
    ReviewDecision,
    Tender,
    TenderRequirement,
    TenderRequirementConflict,
    TenderRequirementEvidence,
)
from app.models.user import User

VALID_OBJECT_TYPES = {"REQUIREMENT", "CONFLICT", "EVIDENCE"}
RATIONALE_REQUIRED_DECISIONS = {"REJECT", "REQUEST_CLARIFICATION", "DISMISS", "RESOLVE", "REOPEN"}

ALLOWED_TRANSITIONS: Dict[str, Dict[str, Tuple[Tuple[str, ...], str]]] = {
    "REQUIREMENT": {
        "CONFIRM": (("DRAFT", "NEEDS_REVIEW", "NEEDS_CLARIFICATION"), "CONFIRMED"),
        "REJECT": (("DRAFT", "NEEDS_REVIEW", "NEEDS_CLARIFICATION"), "REJECTED"),
        "REQUEST_CLARIFICATION": (("DRAFT", "NEEDS_REVIEW", "CONFIRMED"), "NEEDS_CLARIFICATION"),
        "REOPEN": (("CONFIRMED", "REJECTED", "NEEDS_CLARIFICATION"), "NEEDS_REVIEW"),
    },
    "CONFLICT": {
        "CONFIRM": (("DETECTED", "NEEDS_REVIEW"), "CONFIRMED"),
        "DISMISS": (("DETECTED", "NEEDS_REVIEW", "CONFIRMED"), "DISMISSED"),
        "RESOLVE": (("DETECTED", "NEEDS_REVIEW", "CONFIRMED"), "RESOLVED"),
        "REOPEN": (("CONFIRMED", "DISMISSED", "RESOLVED"), "NEEDS_REVIEW"),
    },
    "EVIDENCE": {
        "CONFIRM": (("SUGGESTED", "NEEDS_REVIEW"), "CONFIRMED"),
        "REJECT": (("SUGGESTED", "NEEDS_REVIEW"), "REJECTED"),
        "REOPEN": (("CONFIRMED", "REJECTED"), "NEEDS_REVIEW"),
    },
}


def _validate_rationale(decision_type: str, rationale: Optional[str]) -> str:
    cleaned = (rationale or "").strip()
    if decision_type in RATIONALE_REQUIRED_DECISIONS:
        if len(cleaned) < 5:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"A meaningful rationale (at least 5 characters) is required for {decision_type}.",
            )
    if len(cleaned) > 2000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rationale must not exceed 2000 characters.",
        )
    return cleaned or f"Human {decision_type.lower()} decision recorded."


class TenderReviewService:
    """Atomic, optimistic-concurrency-protected human review workflow service."""

    @staticmethod
    def _model_for_type(object_type: str):
        otype = object_type.strip().upper()
        if otype == "REQUIREMENT":
            return TenderRequirement, "review_status"
        if otype == "CONFLICT":
            return TenderRequirementConflict, "status"
        if otype == "EVIDENCE":
            return TenderRequirementEvidence, "mapping_status"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid review object_type. Expected REQUIREMENT, CONFLICT, or EVIDENCE.",
        )

    @classmethod
    async def submit_decision(
        cls,
        db: AsyncSession,
        tender: Tender,
        actor: User,
        object_type: str,
        object_id: UUID,
        decision_type: str,
        expected_version: int,
        rationale: Optional[str] = None,
    ) -> Tuple[Any, ReviewDecision]:
        otype = object_type.strip().upper()
        dtype = decision_type.strip().upper()
        model_cls, status_attr = cls._model_for_type(otype)

        transitions = ALLOWED_TRANSITIONS[otype]
        if dtype not in transitions:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Decision '{dtype}' is not supported for {otype}.",
            )

        clean_rationale = _validate_rationale(dtype, rationale)

        obj = (
            await db.execute(
                select(model_cls).where(model_cls.id == object_id, model_cls.tender_id == tender.id)
            )
        ).scalar_one_or_none()
        if not obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{otype} review item not found.")

        current_status = getattr(obj, status_attr)
        allowed_from, target_status = transitions[dtype]

        if current_status not in allowed_from:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot apply '{dtype}' from status '{current_status}' on {otype}.",
            )

        if otype == "REQUIREMENT" and dtype == "CONFIRM" and obj.provenance_status == "SOURCE_CHANGED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot confirm requirement while provenance_status is SOURCE_CHANGED; reopen or re-verify source first.",
            )

        if int(obj.review_version) != int(expected_version):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Stale review version: item was updated by another reviewer. Refresh and retry.",
            )

        now = datetime.now(timezone.utc)
        update_values: Dict[str, Any] = {
            status_attr: target_status,
            "review_version": int(expected_version) + 1,
        }
        if otype == "REQUIREMENT":
            update_values["last_reviewed_by_user_id"] = actor.id
            update_values["last_reviewed_at"] = now
        else:
            update_values["reviewed_by_user_id"] = actor.id
            update_values["reviewed_at"] = now

        res = await db.execute(
            update(model_cls)
            .where(
                model_cls.id == object_id,
                model_cls.tender_id == tender.id,
                model_cls.review_version == expected_version,
            )
            .values(**update_values)
        )
        if res.rowcount != 1:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Concurrent review conflict detected. Refresh and retry.",
            )

        decision_rec = ReviewDecision(
            organization_id=tender.organization_id,
            tender_id=tender.id,
            object_type=otype,
            object_id=object_id,
            reviewer_user_id=actor.id,
            decision_type=dtype,
            previous_status=current_status,
            new_status=target_status,
            rationale=clean_rationale,
            object_version=int(expected_version) + 1,
            source_document_sha256=getattr(obj, "source_document_sha256", None),
        )
        db.add(decision_rec)
        db.add(
            AuditLog(
                organization_id=tender.organization_id,
                user_id=actor.id,
                action=f"REVIEW_{dtype}",
                target_type=otype,
                target_id=str(object_id),
                diff_json={
                    "previous_status": current_status,
                    "new_status": target_status,
                    "object_version": int(expected_version) + 1,
                },
            )
        )
        await db.commit()
        await db.refresh(decision_rec)
        updated_obj = (
            await db.execute(select(model_cls).where(model_cls.id == object_id))
        ).scalar_one()
        return updated_obj, decision_rec

    @classmethod
    async def assign_reviewer(
        cls,
        db: AsyncSession,
        tender: Tender,
        actor: User,
        object_type: str,
        object_id: UUID,
        assignee_user_id: Optional[UUID],
        expected_version: int,
        rationale: Optional[str] = None,
    ) -> Tuple[Any, ReviewDecision]:
        otype = object_type.strip().upper()
        model_cls, status_attr = cls._model_for_type(otype)

        if assignee_user_id is not None:
            assignee = (
                await db.execute(
                    select(User)
                    .where(
                        User.id == assignee_user_id,
                        User.organization_id == tender.organization_id,
                        User.is_active == True,  # noqa: E712
                    )
                    .options(
                        selectinload(User.user_roles)
                        .selectinload(UserRole.role)
                        .selectinload(Role.role_permissions)
                        .selectinload(RolePermission.permission)
                    )
                )
            ).scalar_one_or_none()
            if not assignee:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Active organization reviewer not found for this tender's organization.",
                )
            assignee_roles = {
                ur.role.name for ur in (assignee.user_roles or []) if ur.role is not None
            }
            assignee_perms = {
                rp.permission.name
                for ur in (assignee.user_roles or [])
                if ur.role is not None
                for rp in (ur.role.role_permissions or [])
                if rp.permission is not None
            }
            if "SUPER_ADMIN" not in assignee_roles and "evaluation:override" not in assignee_perms:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Selected assignee does not have 'evaluation:override' review permission.",
                )

        obj = (
            await db.execute(
                select(model_cls).where(model_cls.id == object_id, model_cls.tender_id == tender.id)
            )
        ).scalar_one_or_none()
        if not obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{otype} review item not found.")

        if int(obj.review_version) != int(expected_version):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Stale review version during assignment. Refresh and retry.",
            )

        cur_status = getattr(obj, status_attr)
        res = await db.execute(
            update(model_cls)
            .where(
                model_cls.id == object_id,
                model_cls.tender_id == tender.id,
                model_cls.review_version == expected_version,
            )
            .values(
                assigned_reviewer_id=assignee_user_id,
                review_version=int(expected_version) + 1,
            )
        )
        if res.rowcount != 1:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Concurrent assignment conflict detected. Refresh and retry.",
            )

        clean_rationale = (rationale or "").strip() or (
            f"Assigned to reviewer {assignee_user_id}" if assignee_user_id else "Unassigned reviewer"
        )
        decision_rec = ReviewDecision(
            organization_id=tender.organization_id,
            tender_id=tender.id,
            object_type=otype,
            object_id=object_id,
            reviewer_user_id=actor.id,
            decision_type="ASSIGN",
            previous_status=cur_status,
            new_status=cur_status,
            rationale=clean_rationale[:2000],
            object_version=int(expected_version) + 1,
            assigned_to_user_id=assignee_user_id,
        )
        db.add(decision_rec)
        db.add(
            AuditLog(
                organization_id=tender.organization_id,
                user_id=actor.id,
                action="REVIEW_ASSIGNED",
                target_type=otype,
                target_id=str(object_id),
                diff_json={"assigned_to": str(assignee_user_id) if assignee_user_id else None},
            )
        )
        await db.commit()
        await db.refresh(decision_rec)
        updated_obj = (
            await db.execute(select(model_cls).where(model_cls.id == object_id))
        ).scalar_one()
        return updated_obj, decision_rec

    @classmethod
    async def list_review_queue(
        cls,
        db: AsyncSession,
        tender_id: UUID,
        object_type: Optional[str] = None,
        review_status: Optional[str] = None,
        primary_category: Optional[str] = None,
        provenance_status: Optional[str] = None,
        severity: Optional[str] = None,
        assigned_reviewer_id: Optional[UUID] = None,
        unassigned_only: bool = False,
        source_document_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        otype_filter = object_type.strip().upper() if object_type else None
        status_filter = review_status.strip().upper() if review_status else None
        items: List[Dict[str, Any]] = []

        if otype_filter in (None, "REQUIREMENT"):
            conds = [TenderRequirement.tender_id == tender_id]
            if status_filter:
                conds.append(TenderRequirement.review_status == status_filter)
            if primary_category:
                conds.append(TenderRequirement.primary_category == primary_category.strip().upper())
            if provenance_status:
                conds.append(TenderRequirement.provenance_status == provenance_status.strip().upper())
            if assigned_reviewer_id:
                conds.append(TenderRequirement.assigned_reviewer_id == assigned_reviewer_id)
            if unassigned_only:
                conds.append(TenderRequirement.assigned_reviewer_id.is_(None))
            if source_document_id:
                conds.append(TenderRequirement.source_document_id == source_document_id)

            rows = (await db.execute(select(TenderRequirement).where(*conds))).scalars().all()
            for r in rows:
                items.append({
                    "object_type": "REQUIREMENT",
                    "object_id": r.id,
                    "tender_id": r.tender_id,
                    "title": f"{r.requirement_code} · {r.primary_category}",
                    "summary": r.normalized_statement,
                    "status": r.review_status,
                    "review_version": r.review_version,
                    "assigned_reviewer_id": r.assigned_reviewer_id,
                    "primary_category": r.primary_category,
                    "provenance_status": r.provenance_status,
                    "severity": None,
                    "source_document_id": r.source_document_id,
                    "source_page_number": r.source_page_number,
                    "updated_at": r.updated_at,
                })

        if otype_filter in (None, "CONFLICT") and not primary_category and not provenance_status and not source_document_id:
            conds = [TenderRequirementConflict.tender_id == tender_id]
            if status_filter:
                conds.append(TenderRequirementConflict.status == status_filter)
            if severity:
                conds.append(TenderRequirementConflict.severity == severity.strip().upper())
            if assigned_reviewer_id:
                conds.append(TenderRequirementConflict.assigned_reviewer_id == assigned_reviewer_id)
            if unassigned_only:
                conds.append(TenderRequirementConflict.assigned_reviewer_id.is_(None))

            rows = (await db.execute(select(TenderRequirementConflict).where(*conds))).scalars().all()
            for c in rows:
                items.append({
                    "object_type": "CONFLICT",
                    "object_id": c.id,
                    "tender_id": c.tender_id,
                    "title": f"{c.conflict_type} · {c.severity}",
                    "summary": c.explanation,
                    "status": c.status,
                    "review_version": c.review_version,
                    "assigned_reviewer_id": c.assigned_reviewer_id,
                    "primary_category": None,
                    "provenance_status": None,
                    "severity": c.severity,
                    "source_document_id": None,
                    "source_page_number": None,
                    "updated_at": c.updated_at,
                })

        if otype_filter in (None, "EVIDENCE") and not primary_category and not provenance_status and not severity and not source_document_id:
            conds = [TenderRequirementEvidence.tender_id == tender_id]
            if status_filter:
                conds.append(TenderRequirementEvidence.mapping_status == status_filter)
            if assigned_reviewer_id:
                conds.append(TenderRequirementEvidence.assigned_reviewer_id == assigned_reviewer_id)
            if unassigned_only:
                conds.append(TenderRequirementEvidence.assigned_reviewer_id.is_(None))

            rows = (await db.execute(select(TenderRequirementEvidence).where(*conds))).scalars().all()
            for e in rows:
                items.append({
                    "object_type": "EVIDENCE",
                    "object_id": e.id,
                    "tender_id": e.tender_id,
                    "title": f"{e.evidence_type} · {e.expected_document_name}",
                    "summary": e.evidence_purpose,
                    "status": e.mapping_status,
                    "review_version": e.review_version,
                    "assigned_reviewer_id": e.assigned_reviewer_id,
                    "primary_category": None,
                    "provenance_status": None,
                    "severity": None,
                    "source_document_id": None,
                    "source_page_number": None,
                    "updated_at": e.updated_at,
                })

        items.sort(key=lambda x: x["updated_at"], reverse=True)
        total = len(items)
        return total, items[offset : offset + limit]

    @classmethod
    async def get_workload_summary(cls, db: AsyncSession, tender_id: UUID) -> Dict[str, Any]:
        reqs = (await db.execute(select(TenderRequirement).where(TenderRequirement.tender_id == tender_id))).scalars().all()
        confs = (await db.execute(select(TenderRequirementConflict).where(TenderRequirementConflict.tender_id == tender_id))).scalars().all()
        evs = (await db.execute(select(TenderRequirementEvidence).where(TenderRequirementEvidence.tender_id == tender_id))).scalars().all()

        pending_statuses = {"DRAFT", "NEEDS_REVIEW", "DETECTED", "SUGGESTED"}
        pending = (
            sum(1 for r in reqs if r.review_status in pending_statuses)
            + sum(1 for c in confs if c.status in pending_statuses)
            + sum(1 for e in evs if e.mapping_status in pending_statuses)
        )
        confirmed = (
            sum(1 for r in reqs if r.review_status == "CONFIRMED")
            + sum(1 for c in confs if c.status == "CONFIRMED")
            + sum(1 for e in evs if e.mapping_status == "CONFIRMED")
        )
        rejected = (
            sum(1 for r in reqs if r.review_status == "REJECTED")
            + sum(1 for e in evs if e.mapping_status == "REJECTED")
        )
        needs_clarification = sum(1 for r in reqs if r.review_status == "NEEDS_CLARIFICATION")
        unassigned = (
            sum(1 for r in reqs if r.assigned_reviewer_id is None)
            + sum(1 for c in confs if c.assigned_reviewer_id is None)
            + sum(1 for e in evs if e.assigned_reviewer_id is None)
        )
        return {
            "tender_id": tender_id,
            "pending_count": pending,
            "confirmed_count": confirmed,
            "rejected_count": rejected,
            "needs_clarification_count": needs_clarification,
            "conflict_count": len(confs),
            "evidence_count": len(evs),
            "unassigned_count": unassigned,
        }

    @classmethod
    async def invalidate_for_source_change(
        cls,
        db: AsyncSession,
        tender_id: UUID,
        requirement_ids: List[UUID],
        previous_sha256: Optional[str],
        current_sha256: Optional[str],
        reason: Optional[str] = None,
    ) -> int:
        """Atomically invalidate stale human reviews when underlying source material changes."""
        if not requirement_ids:
            return 0

        tender = (await db.execute(select(Tender).where(Tender.id == tender_id))).scalar_one_or_none()
        org_id = tender.organization_id if tender else None
        prev_tag = (previous_sha256 or "unknown")[:12]
        curr_tag = (current_sha256 or "unknown")[:12]
        rationale_text = (
            reason
            or f"Source document SHA-256 changed ({prev_tag} -> {curr_tag}); renewed human review required."
        )[:2000]
        invalidated_count = 0

        reqs = (
            await db.execute(
                select(TenderRequirement).where(
                    TenderRequirement.tender_id == tender_id,
                    TenderRequirement.id.in_(requirement_ids),
                    TenderRequirement.review_status.in_(["CONFIRMED", "REJECTED", "NEEDS_CLARIFICATION"]),
                )
            )
        ).scalars().all()
        for req in reqs:
            old_status = req.review_status
            cur_ver = int(req.review_version)
            res = await db.execute(
                update(TenderRequirement)
                .where(
                    TenderRequirement.id == req.id,
                    TenderRequirement.tender_id == tender_id,
                    TenderRequirement.review_version == cur_ver,
                )
                .values(review_status="NEEDS_REVIEW", review_version=cur_ver + 1)
            )
            if res.rowcount == 1:
                invalidated_count += 1
                db.add(
                    ReviewDecision(
                        organization_id=org_id,
                        tender_id=tender_id,
                        object_type="REQUIREMENT",
                        object_id=req.id,
                        reviewer_user_id=None,
                        decision_type="SOURCE_INVALIDATED",
                        previous_status=old_status,
                        new_status="NEEDS_REVIEW",
                        rationale=rationale_text,
                        object_version=cur_ver + 1,
                        source_document_sha256=current_sha256,
                    )
                )
                db.add(
                    AuditLog(
                        organization_id=org_id,
                        user_id=None,
                        action="REVIEW_SOURCE_INVALIDATED",
                        target_type="REQUIREMENT",
                        target_id=str(req.id),
                        diff_json={
                            "previous_status": old_status,
                            "new_status": "NEEDS_REVIEW",
                            "previous_sha256": previous_sha256,
                            "current_sha256": current_sha256,
                            "object_version": cur_ver + 1,
                        },
                    )
                )

        confs = (
            await db.execute(
                select(TenderRequirementConflict).where(
                    TenderRequirementConflict.tender_id == tender_id,
                    or_(
                        TenderRequirementConflict.requirement_a_id.in_(requirement_ids),
                        TenderRequirementConflict.requirement_b_id.in_(requirement_ids),
                    ),
                    TenderRequirementConflict.status.in_(["CONFIRMED", "DISMISSED", "RESOLVED"]),
                )
            )
        ).scalars().all()
        for conf in confs:
            old_status = conf.status
            cur_ver = int(conf.review_version)
            res = await db.execute(
                update(TenderRequirementConflict)
                .where(
                    TenderRequirementConflict.id == conf.id,
                    TenderRequirementConflict.tender_id == tender_id,
                    TenderRequirementConflict.review_version == cur_ver,
                )
                .values(status="NEEDS_REVIEW", review_version=cur_ver + 1)
            )
            if res.rowcount == 1:
                invalidated_count += 1
                db.add(
                    ReviewDecision(
                        organization_id=org_id,
                        tender_id=tender_id,
                        object_type="CONFLICT",
                        object_id=conf.id,
                        reviewer_user_id=None,
                        decision_type="SOURCE_INVALIDATED",
                        previous_status=old_status,
                        new_status="NEEDS_REVIEW",
                        rationale=rationale_text,
                        object_version=cur_ver + 1,
                        source_document_sha256=current_sha256,
                    )
                )
                db.add(
                    AuditLog(
                        organization_id=org_id,
                        user_id=None,
                        action="REVIEW_SOURCE_INVALIDATED",
                        target_type="CONFLICT",
                        target_id=str(conf.id),
                        diff_json={
                            "previous_status": old_status,
                            "new_status": "NEEDS_REVIEW",
                            "object_version": cur_ver + 1,
                        },
                    )
                )

        evs = (
            await db.execute(
                select(TenderRequirementEvidence).where(
                    TenderRequirementEvidence.tender_id == tender_id,
                    TenderRequirementEvidence.requirement_id.in_(requirement_ids),
                    TenderRequirementEvidence.mapping_status.in_(["CONFIRMED", "REJECTED"]),
                )
            )
        ).scalars().all()
        for ev in evs:
            old_status = ev.mapping_status
            cur_ver = int(ev.review_version)
            res = await db.execute(
                update(TenderRequirementEvidence)
                .where(
                    TenderRequirementEvidence.id == ev.id,
                    TenderRequirementEvidence.tender_id == tender_id,
                    TenderRequirementEvidence.review_version == cur_ver,
                )
                .values(mapping_status="NEEDS_REVIEW", review_version=cur_ver + 1)
            )
            if res.rowcount == 1:
                invalidated_count += 1
                db.add(
                    ReviewDecision(
                        organization_id=org_id,
                        tender_id=tender_id,
                        object_type="EVIDENCE",
                        object_id=ev.id,
                        reviewer_user_id=None,
                        decision_type="SOURCE_INVALIDATED",
                        previous_status=old_status,
                        new_status="NEEDS_REVIEW",
                        rationale=rationale_text,
                        object_version=cur_ver + 1,
                        source_document_sha256=current_sha256,
                    )
                )
                db.add(
                    AuditLog(
                        organization_id=org_id,
                        user_id=None,
                        action="REVIEW_SOURCE_INVALIDATED",
                        target_type="EVIDENCE",
                        target_id=str(ev.id),
                        diff_json={
                            "previous_status": old_status,
                            "new_status": "NEEDS_REVIEW",
                            "object_version": cur_ver + 1,
                        },
                    )
                )

        await db.flush()
        return invalidated_count
