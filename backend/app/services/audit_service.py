import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """Append-only audit logging service for security, compliance, and governance tracking."""

    @classmethod
    async def log_event(
        cls,
        action: str,
        target_type: str,
        target_id: Optional[str],
        db: AsyncSession,
        organization_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        diff_json: Optional[Dict[str, Any]] = None,
        commit: bool = True,
    ) -> AuditLog:
        """Create an append-only audit log entry."""
        entry = AuditLog(
            timestamp=datetime.now(timezone.utc),
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            ip_address=ip_address,
            user_agent=user_agent,
            diff_json=diff_json,
        )
        db.add(entry)
        if commit:
            await db.commit()
            await db.refresh(entry)
        else:
            await db.flush()
        return entry

    @classmethod
    async def get_organization_audit_logs(
        cls,
        organization_id: Optional[UUID],
        db: AsyncSession,
        limit: int = 50,
        offset: int = 0,
        action: Optional[str] = None,
        target_type: Optional[str] = None,
        is_super_admin: bool = False,
    ) -> Tuple[List[AuditLog], int]:
        """Query audit log entries scoped strictly to the organization."""
        stmt = select(AuditLog).options(selectinload(AuditLog.user))

        count_stmt = select(func.count(AuditLog.id))
        if not is_super_admin:
            if organization_id:
                stmt = stmt.where(AuditLog.organization_id == organization_id)
                count_stmt = count_stmt.where(AuditLog.organization_id == organization_id)
            else:
                return [], 0

        if action:
            stmt = stmt.where(AuditLog.action == action)
            count_stmt = count_stmt.where(AuditLog.action == action)
        if target_type:
            stmt = stmt.where(AuditLog.target_type == target_type)
            count_stmt = count_stmt.where(AuditLog.target_type == target_type)

        total = (await db.execute(count_stmt)).scalar() or 0
        stmt = stmt.order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit)
        results = (await db.execute(stmt)).scalars().all()
        return list(results), int(total)
