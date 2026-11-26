from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import InvitationCreateResponse
from app.schemas.organization import (
    MemberRoleUpdateRequest,
    MemberStatusUpdateRequest,
    OrganizationInvitationItemResponse,
    OrganizationInvitationListResponse,
    OrganizationMemberListResponse,
    OrganizationMemberResponse,
    OrganizationProfileResponse,
    OrganizationUpdateRequest,
    RoleSummaryResponse,
)
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/organizations", tags=["Organization & Membership Administration"])


@router.get(
    "/me",
    response_model=OrganizationProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve current user's organization profile and membership summary",
)
async def get_my_organization(
    current_user: User = Depends(require_permission("organization:read")),
    db: AsyncSession = Depends(get_db),
):
    data = await OrganizationService.get_organization_overview(current_user.organization_id, db)
    return OrganizationProfileResponse(**data)


@router.put(
    "/me",
    response_model=OrganizationProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Update editable profile fields for current user's organization",
)
async def update_my_organization(
    payload: OrganizationUpdateRequest,
    current_user: User = Depends(require_permission("organization:update")),
    db: AsyncSession = Depends(get_db),
):
    domain_provided = "domain" in payload.model_fields_set
    data = await OrganizationService.update_organization_profile(
        organization_id=current_user.organization_id,
        actor=current_user,
        name=payload.name,
        domain=payload.domain,
        domain_provided=domain_provided,
        db=db,
    )
    return OrganizationProfileResponse(**data)


@router.get(
    "/roles",
    response_model=List[RoleSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="List platform RBAC roles, permissions, and org-admin assignability",
)
async def list_roles(
    current_user: User = Depends(require_permission("organization:read")),
):
    return [RoleSummaryResponse(**r) for r in OrganizationService.list_role_summaries()]


@router.get(
    "/me/members",
    response_model=OrganizationMemberListResponse,
    status_code=status.HTTP_200_OK,
    summary="List organization members with server-side search, filtering, and pagination",
)
async def list_organization_members(
    q: Optional[str] = Query(None, description="Search by member name or email"),
    role: Optional[str] = Query(None, description="Filter by assigned role name"),
    is_active: Optional[bool] = Query(None, description="Filter by active membership status"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("organization:read")),
    db: AsyncSession = Depends(get_db),
):
    items, total = await OrganizationService.list_members(
        organization_id=current_user.organization_id,
        db=db,
        q=q,
        role=role,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    return OrganizationMemberListResponse(
        items=[OrganizationMemberResponse(**i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put(
    "/me/members/{user_id}/role",
    response_model=OrganizationMemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a team member's organization role",
)
async def update_member_role(
    user_id: UUID,
    payload: MemberRoleUpdateRequest,
    current_user: User = Depends(require_permission("user:manage")),
    db: AsyncSession = Depends(get_db),
):
    item = await OrganizationService.update_member_role(
        organization_id=current_user.organization_id,
        target_user_id=user_id,
        role_name=payload.role_name,
        actor=current_user,
        db=db,
    )
    return OrganizationMemberResponse(**item)


@router.put(
    "/me/members/{user_id}/status",
    response_model=OrganizationMemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Deactivate or reactivate an organization member",
)
async def update_member_status(
    user_id: UUID,
    payload: MemberStatusUpdateRequest,
    current_user: User = Depends(require_permission("user:manage")),
    db: AsyncSession = Depends(get_db),
):
    item = await OrganizationService.update_member_status(
        organization_id=current_user.organization_id,
        target_user_id=user_id,
        is_active=payload.is_active,
        actor=current_user,
        db=db,
    )
    return OrganizationMemberResponse(**item)


@router.delete(
    "/me/members/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove a member from the organization",
)
async def remove_member(
    user_id: UUID,
    current_user: User = Depends(require_permission("user:manage")),
    db: AsyncSession = Depends(get_db),
):
    await OrganizationService.remove_member(
        organization_id=current_user.organization_id,
        target_user_id=user_id,
        actor=current_user,
        db=db,
    )
    return {"message": "Member removed successfully."}


@router.get(
    "/me/invitations",
    response_model=OrganizationInvitationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List organization invitations with computed lifecycle status",
)
async def list_invitations(
    status_filter: Optional[str] = Query(None, alias="status", description="PENDING, ACCEPTED, EXPIRED, REVOKED"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("user:invite")),
    db: AsyncSession = Depends(get_db),
):
    items, total = await OrganizationService.list_invitations(
        organization_id=current_user.organization_id,
        db=db,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return OrganizationInvitationListResponse(
        items=[OrganizationInvitationItemResponse(**i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/me/invitations/{invitation_id}/revoke",
    response_model=OrganizationInvitationItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke a pending organization invitation",
)
async def revoke_invitation(
    invitation_id: UUID,
    current_user: User = Depends(require_permission("user:invite")),
    db: AsyncSession = Depends(get_db),
):
    item = await OrganizationService.revoke_invitation(
        organization_id=current_user.organization_id,
        invitation_id=invitation_id,
        actor=current_user,
        db=db,
    )
    return OrganizationInvitationItemResponse(**item)


@router.post(
    "/me/invitations/{invitation_id}/resend",
    response_model=InvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Revoke previous pending invitation and issue a fresh single-use invitation",
)
async def resend_invitation(
    invitation_id: UUID,
    current_user: User = Depends(require_permission("user:invite")),
    db: AsyncSession = Depends(get_db),
):
    raw_token, inv = await OrganizationService.resend_invitation(
        organization_id=current_user.organization_id,
        invitation_id=invitation_id,
        actor=current_user,
        db=db,
    )
    return InvitationCreateResponse(
        id=inv.id,
        email=inv.email,
        role_name=inv.role_name,
        organization_id=inv.organization_id,
        expires_at=inv.expires_at,
        invitation_token=raw_token,
    )
