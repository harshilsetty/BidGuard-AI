from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class UserRegisterRequest(BaseModel):
    """User and organization registration payload."""
    email: str = Field(..., min_length=5, max_length=255, description="Valid enterprise email address")
    password: str = Field(..., min_length=8, description="Minimum 8 characters with mixed case and numbers")
    full_name: str = Field(..., min_length=2, max_length=255)
    organization_name: str = Field(..., min_length=2, max_length=255)
    organization_slug: Optional[str] = Field(None, min_length=2, max_length=100)
    domain: Optional[str] = Field(None, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if "@" not in v_clean or "." not in v_clean.split("@")[-1]:
            raise ValueError("Invalid email format.")
        return v_clean


class UserLoginRequest(BaseModel):
    """User authentication payload."""
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    """Access token payload returned to client."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: UUID
    organization_id: UUID
    roles: List[str]
    permissions: List[str]


class RefreshTokenRequest(BaseModel):
    """Optional request body for clients unable to use HttpOnly cookies."""
    refresh_token: Optional[str] = None


class OrganizationResponse(BaseModel):
    """Organization metadata view."""
    id: UUID
    name: str
    slug: str
    domain: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class InvitationCreateRequest(BaseModel):
    """Admin-initiated single-use organization invitation request."""
    email: str = Field(..., min_length=5, max_length=255)
    role_name: str = Field(..., min_length=2, max_length=50)

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if "@" not in v_clean or "." not in v_clean.split("@")[-1]:
            raise ValueError("Invalid email format.")
        return v_clean


class InvitationCreateResponse(BaseModel):
    """Invitation creation response (notes email delivery configuration status)."""
    id: UUID
    email: str
    role_name: str
    organization_id: UUID
    expires_at: datetime
    invitation_token: str
    email_delivery_status: str = "NOT_CONFIGURED_OUT_OF_BAND_DELIVERY_REQUIRED"


class InvitationAcceptRequest(BaseModel):
    """Accept an expiring single-use invitation."""
    invitation_token: str = Field(..., min_length=16)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class InvitationValidateResponse(BaseModel):
    """Safe invitation metadata returned during pre-acceptance validation."""
    valid: bool
    status: str  # PENDING | EXPIRED | REVOKED | ACCEPTED | INVALID
    organization_name: Optional[str] = None
    role_name: Optional[str] = None
    email_masked: Optional[str] = None
    expires_at: Optional[datetime] = None
    requires_existing_login: bool = False


class UserProfileResponse(BaseModel):
    """Current authenticated user profile view."""
    id: UUID
    email: str
    full_name: str
    organization_id: UUID
    organization_name: str
    roles: List[str]
    permissions: List[str]
    is_active: bool
    is_verified: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
