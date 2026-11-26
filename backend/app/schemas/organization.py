from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class OrganizationProfileResponse(BaseModel):
    """Organization profile and operational summary for authenticated members."""
    id: UUID
    name: str
    slug: str
    domain: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    total_members: int
    active_members: int
    pending_invitations: int


class OrganizationUpdateRequest(BaseModel):
    """Editable organization profile fields (system-managed fields excluded)."""
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    domain: Optional[str] = Field(None, max_length=255)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Organization name must be at least 2 characters.")
        return cleaned

    @field_validator("domain")
    @classmethod
    def clean_domain(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().lower()
        return cleaned or None


class RoleSummaryResponse(BaseModel):
    """System role definition and assigned permissions."""
    name: str
    description: str
    scope: str
    assignable_by_org_admin: bool
    permissions: List[str]


class OrganizationMemberResponse(BaseModel):
    """Organization member row."""
    id: UUID
    email: str
    full_name: str
    organization_id: UUID
    roles: List[str]
    is_active: bool
    is_verified: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime


class OrganizationMemberListResponse(BaseModel):
    """Paginated organization members list."""
    items: List[OrganizationMemberResponse]
    total: int
    limit: int
    offset: int


class MemberRoleUpdateRequest(BaseModel):
    """Update a member's organization role."""
    role_name: str = Field(..., min_length=2, max_length=50)


class MemberStatusUpdateRequest(BaseModel):
    """Activate or deactivate an organization member."""
    is_active: bool


class OrganizationInvitationItemResponse(BaseModel):
    """Invitation record with computed lifecycle status (never exposes token_hash)."""
    id: UUID
    organization_id: UUID
    email: str
    role_name: str
    status: str  # PENDING | ACCEPTED | EXPIRED | REVOKED
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    invited_by_user_id: Optional[UUID] = None
    created_at: datetime


class OrganizationInvitationListResponse(BaseModel):
    """Paginated organization invitations list."""
    items: List[OrganizationInvitationItemResponse]
    total: int
    limit: int
    offset: int
