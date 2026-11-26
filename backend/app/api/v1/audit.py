from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_active_user, require_permission
from app.models.user import User
from app.schemas.audit import AuditLogListResponse, AuditLogEntryResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["Security & Compliance Audit Logging"])


@router.get(
    "/logs",
    response_model=AuditLogListResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve append-only audit trail scoped to user organization",
)
async def get_audit_logs(
    action: Optional[str] = Query(None, description="Filter by event action"),
    target_type: Optional[str] = Query(None, description="Filter by target entity type"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("audit:read")),
    db: AsyncSession = Depends(get_db),
):
    user_roles = getattr(current_user, "token_roles", [])
    is_super = "SUPER_ADMIN" in user_roles

    logs, total = await AuditService.get_organization_audit_logs(
        organization_id=current_user.organization_id,
        db=db,
        limit=limit,
        offset=offset,
        action=action,
        target_type=target_type,
        is_super_admin=is_super,
    )

    items = []
    for log in logs:
        items.append(
            AuditLogEntryResponse(
                id=log.id,
                timestamp=log.timestamp,
                organization_id=log.organization_id,
                user_id=log.user_id,
                user_email=log.user.email if log.user else None,
                action=log.action,
                target_type=log.target_type,
                target_id=log.target_id,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                diff_json=log.diff_json,
            )
        )

    return AuditLogListResponse(items=items, total=total)
