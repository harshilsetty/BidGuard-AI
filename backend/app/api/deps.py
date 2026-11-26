from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.models.organization import Organization
from app.models.rbac import UserRole, Role, RolePermission, Permission
from app.models.tender import Tender
from app.models.bidder import Bidder, BidDocument
from app.models.clause import TenderClause
from app.models.evaluation import ComplianceEvaluation

# Bearer token extractor
security_scheme = HTTPBearer(auto_error=False)


async def get_token_payload(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
) -> Dict[str, Any]:
    """Extract and validate JWT access token from Authorization header."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
        return payload
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


def _resolve_live_roles_and_permissions(user: User) -> Tuple[List[str], List[str]]:
    """Compute authoritative roles and permissions from live DB UserRole relations."""
    roles: Set[str] = set()
    permissions: Set[str] = set()
    for ur in getattr(user, "user_roles", []) or []:
        if ur.role:
            roles.add(ur.role.name)
            for rp in getattr(ur.role, "role_permissions", []) or []:
                if rp.permission:
                    permissions.add(rp.permission.name)
    return sorted(roles), sorted(permissions)


async def get_current_user(
    payload: Dict[str, Any] = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Retrieve and validate the authenticated user and live DB permissions."""
    try:
        user_id = UUID(payload["sub"])
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token claims.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.organization),
            selectinload(User.user_roles)
            .selectinload(UserRole.role)
            .selectinload(Role.role_permissions)
            .selectinload(RolePermission.permission),
        )
    )
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    if user.organization and not user.organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is deactivated.",
        )

    # F-06 Fix: Live DB roles & permissions are authoritative, preventing stale JWT privileges
    live_roles, live_permissions = _resolve_live_roles_and_permissions(user)
    setattr(user, "live_roles", live_roles)
    setattr(user, "live_permissions", live_permissions)
    setattr(user, "token_roles", live_roles)
    setattr(user, "token_permissions", live_permissions)

    # Set transaction-local PostgreSQL RLS tenant context (automatically cleared on commit/rollback)
    if db.bind and db.bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(user.organization_id or "")},
        )
        await db.execute(
            text("SELECT set_config('app.is_super_admin', :is_sa, true)"),
            {"is_sa": "true" if "SUPER_ADMIN" in live_roles else "false"},
        )

    return user


async def get_current_active_user(
    user: User = Depends(get_current_user),
) -> User:
    """Ensure user is active and ready for business operations."""
    return user


def require_permission(permission: str) -> Callable:
    """FastAPI dependency factory enforcing server-side live DB permission checks."""
    async def permission_dependency(
        user: User = Depends(get_current_active_user),
    ) -> User:
        user_roles = getattr(user, "live_roles", [])
        if "SUPER_ADMIN" in user_roles:
            return user  # Platform-wide governance

        user_perms = getattr(user, "live_permissions", [])
        if permission not in user_perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Missing required permission '{permission}'.",
            )
        return user

    return permission_dependency


def require_role(role_name: str) -> Callable:
    """FastAPI dependency factory enforcing live DB role membership."""
    async def role_dependency(
        user: User = Depends(get_current_active_user),
    ) -> User:
        user_roles = getattr(user, "live_roles", [])
        if "SUPER_ADMIN" in user_roles:
            return user

        if role_name not in user_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: User does not hold role '{role_name}'.",
            )
        return user

    return role_dependency


async def get_current_tenant(
    user: User = Depends(get_current_active_user),
) -> UUID:
    """Extract authenticated tenant (organization) ID for multi-tenant scoping."""
    if not user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with an active organization.",
        )
    return user.organization_id


# ---------------------------------------------------------------------------
# Centralized Tenant Ownership Validators (Workstream A)
# ---------------------------------------------------------------------------

def validate_tender_tenant_access(tender: Tender, user: User) -> None:
    """Enforce strict multi-tenant boundary on a Tender record.

    - Unauthenticated callers are rejected (401).
    - Legacy/unassigned tenders (organization_id IS NULL) are blocked from ordinary tenant APIs (404).
    - Cross-tenant access returns 404 to prevent UUID enumeration.
    - SUPER_ADMIN has explicit platform-level governance access.
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_roles = getattr(user, "live_roles", [])
    if "SUPER_ADMIN" in user_roles:
        return
    if tender.organization_id is None or tender.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender not found",
        )


async def get_authorized_tender(
    tender_id: UUID,
    user: User,
    db: AsyncSession,
) -> Tender:
    """Fetch a Tender by ID and validate tenant ownership."""
    stmt = select(Tender).where(Tender.id == tender_id)
    tender = (await db.execute(stmt)).scalar_one_or_none()
    if not tender:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender not found",
        )
    validate_tender_tenant_access(tender, user)
    return tender


async def validate_bidder_tenant_access(
    bidder_id: UUID,
    tender_id: Optional[UUID],
    user: User,
    db: AsyncSession,
) -> Tuple[Bidder, Tender]:
    """Validate ownership through Bidder -> Tender -> Organization."""
    stmt = (
        select(Bidder)
        .where(Bidder.id == bidder_id)
        .options(selectinload(Bidder.tender))
    )
    bidder = (await db.execute(stmt)).scalar_one_or_none()
    if not bidder or not bidder.tender:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bidder not found",
        )
    if tender_id and bidder.tender_id != tender_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bidder not found for this tender",
        )
    validate_tender_tenant_access(bidder.tender, user)
    return bidder, bidder.tender


async def validate_document_tenant_access(
    document_id: UUID,
    user: User,
    db: AsyncSession,
) -> Tuple[BidDocument, Bidder, Tender]:
    """Validate ownership through BidDocument -> Bidder -> Tender -> Organization."""
    stmt = (
        select(BidDocument)
        .where(BidDocument.id == document_id)
        .options(selectinload(BidDocument.bidder).selectinload(Bidder.tender))
    )
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if not doc or not doc.bidder or not doc.bidder.tender:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    validate_tender_tenant_access(doc.bidder.tender, user)
    return doc, doc.bidder, doc.bidder.tender


async def validate_evaluation_tenant_access(
    evaluation_id: UUID,
    tender_id: Optional[UUID],
    user: User,
    db: AsyncSession,
) -> ComplianceEvaluation:
    """Validate ownership through ComplianceEvaluation -> TenderClause -> Tender -> Organization."""
    stmt = (
        select(ComplianceEvaluation)
        .where(ComplianceEvaluation.id == evaluation_id)
        .options(
            selectinload(ComplianceEvaluation.clause).selectinload(TenderClause.tender),
            selectinload(ComplianceEvaluation.bidder),
        )
    )
    eval_rec = (await db.execute(stmt)).scalar_one_or_none()
    if not eval_rec or not eval_rec.clause or not eval_rec.clause.tender:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Compliance evaluation {evaluation_id} not found",
        )
    if tender_id and eval_rec.clause.tender_id != tender_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation {evaluation_id} does not belong to tender {tender_id}",
        )
    validate_tender_tenant_access(eval_rec.clause.tender, user)
    return eval_rec
