import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Dict, Optional
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.api.deps import get_current_active_user, require_permission
from app.models.user import User
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    UserProfileResponse,
    InvitationCreateRequest,
    InvitationCreateResponse,
    InvitationAcceptRequest,
    InvitationValidateResponse,
)
from app.services.auth_service import AuthService
from app.services.rbac_service import RBACService

router = APIRouter(prefix="/auth", tags=["Enterprise Authentication"])

COOKIE_NAME = "bidguard_refresh_token"

# Sliding-window in-memory rate limiter for auth endpoints
_AUTH_RATE_BUCKETS: Dict[str, deque] = defaultdict(deque)
AUTH_RATE_LIMIT_MAX = 30
AUTH_RATE_LIMIT_WINDOW_SEC = 60


def reset_auth_rate_limiter() -> None:
    """Reset in-memory rate limiter buckets (for deterministic testing)."""
    _AUTH_RATE_BUCKETS.clear()


def _enforce_rate_limit(request: Request, action: str) -> None:
    client_ip = request.client.host if request.client else "unknown"
    key = f"{action}:{client_ip}"
    now = time.monotonic()
    bucket = _AUTH_RATE_BUCKETS[key]
    while bucket and (now - bucket[0]) > AUTH_RATE_LIMIT_WINDOW_SEC:
        bucket.popleft()
    if len(bucket) >= AUTH_RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication requests. Please retry later.",
        )
    bucket.append(now)


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Helper to set secure, HttpOnly refresh token cookie."""
    max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
    response.set_cookie(
        key=COOKIE_NAME,
        value=refresh_token,
        max_age=max_age,
        expires=max_age,
        path="/api/v1/auth",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Helper to delete the refresh token cookie."""
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/api/v1/auth",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Restricted organization registration (disabled by default; use invitations)",
)
async def register(
    payload: UserRegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    _enforce_rate_limit(request, "register")
    if not settings.ALLOW_PUBLIC_ORG_SIGNUP:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public organization registration is disabled. Use an organization invitation or administrator bootstrap.",
        )

    ip_addr = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    access_token, raw_refresh, user, org, roles, perms = (
        await AuthService.register_organization_and_admin(
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            organization_name=payload.organization_name,
            organization_slug=payload.organization_slug,
            domain=payload.domain,
            db=db,
            ip_address=ip_addr,
            user_agent=user_agent,
        )
    )

    _set_refresh_cookie(response, raw_refresh)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user.id,
        organization_id=org.id,
        roles=roles,
        permissions=perms,
    )


@router.post(
    "/invitations",
    response_model=InvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create single-use expiring organization invitation (requires user:invite)",
)
async def create_invitation(
    payload: InvitationCreateRequest,
    current_user: User = Depends(require_permission("user:invite")),
    db: AsyncSession = Depends(get_db),
):
    raw_token, inv = await AuthService.create_invitation(
        organization_id=current_user.organization_id,
        email=payload.email,
        role_name=payload.role_name,
        invited_by=current_user,
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


@router.get(
    "/invitations/validate",
    response_model=InvitationValidateResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate an invitation token before acceptance",
)
async def validate_invitation(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _enforce_rate_limit(request, "invite_validate")
    result = await AuthService.validate_invitation_token(token, db)
    return InvitationValidateResponse(**result)


@router.post(
    "/invitations/accept",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Accept single-use organization invitation and create user session",
)
async def accept_invitation(
    payload: InvitationAcceptRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    _enforce_rate_limit(request, "invite_accept")
    ip_addr = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    access_token, raw_refresh, user, org, roles, perms = (
        await AuthService.accept_invitation(
            invitation_token=payload.invitation_token,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            db=db,
            ip_address=ip_addr,
            user_agent=user_agent,
        )
    )
    _set_refresh_cookie(response, raw_refresh)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user.id,
        organization_id=org.id,
        roles=roles,
        permissions=perms,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and issue access and refresh tokens",
)
async def login(
    payload: UserLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    _enforce_rate_limit(request, "login")
    ip_addr = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    access_token, raw_refresh, user, org, roles, perms = (
        await AuthService.authenticate_user(
            email=payload.email,
            password=payload.password,
            db=db,
            ip_address=ip_addr,
            user_agent=user_agent,
        )
    )

    _set_refresh_cookie(response, raw_refresh)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user.id,
        organization_id=org.id,
        roles=roles,
        permissions=perms,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Atomically rotate refresh token and obtain new access token",
)
async def refresh_token(
    request: Request,
    response: Response,
    body: Optional[RefreshTokenRequest] = None,
    bidguard_refresh_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    _enforce_rate_limit(request, "refresh")
    raw_token = bidguard_refresh_token or (body.refresh_token if body else None)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found in cookie or request body.",
        )

    ip_addr = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    access_token, new_raw_refresh, user, org, roles, perms = (
        await AuthService.rotate_refresh_token(
            raw_refresh_token=raw_token,
            db=db,
            ip_address=ip_addr,
            user_agent=user_agent,
        )
    )

    _set_refresh_cookie(response, new_raw_refresh)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user.id,
        organization_id=org.id,
        roles=roles,
        permissions=perms,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Revoke session and invalidate refresh token",
)
async def logout(
    request: Request,
    response: Response,
    body: Optional[RefreshTokenRequest] = None,
    bidguard_refresh_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    raw_token = bidguard_refresh_token or (body.refresh_token if body else None)
    ip_addr = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    await AuthService.revoke_session(
        raw_refresh_token=raw_token,
        db=db,
        ip_address=ip_addr,
        user_agent=user_agent,
    )

    _clear_refresh_cookie(response)
    return {"message": "Logged out successfully. Session invalidated."}


@router.get(
    "/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve profile and permissions for currently authenticated user",
)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    roles, perms = await RBACService.get_user_roles_and_permissions(current_user.id, db)
    org_name = current_user.organization.name if current_user.organization else "Platform Admin"

    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        organization_id=current_user.organization_id,
        organization_name=org_name,
        roles=roles,
        permissions=perms,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        last_login_at=current_user.last_login_at,
        created_at=current_user.created_at,
    )
