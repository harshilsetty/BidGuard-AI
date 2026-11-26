import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    validate_password_strength,
    generate_secure_token,
    hash_token,
    create_access_token,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.auth import RefreshToken, OrganizationInvitation
from app.models.rbac import Role, UserRole
from app.models.audit import AuditLog
from app.services.rbac_service import RBACService


class AuthService:
    """Enterprise authentication and session management service."""

    @staticmethod
    async def _enable_auth_lookup(db: AsyncSession, org_id: Optional[UUID] = None) -> None:
        """Enable transaction-local auth_lookup (and optional org_id) for PostgreSQL RLS during pre-auth queries."""
        if db.bind and db.bind.dialect.name == "postgresql":
            await db.execute(text("SELECT set_config('app.auth_lookup', 'true', true)"))
            if org_id is not None:
                await db.execute(
                    text("SELECT set_config('app.current_org_id', :org_id, true)"),
                    {"org_id": str(org_id)},
                )

    @classmethod
    async def register_organization_and_admin(
        cls,
        email: str,
        password: str,
        full_name: str,
        organization_name: str,
        organization_slug: Optional[str],
        domain: Optional[str],
        db: AsyncSession,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[str, str, User, Organization, List[str], List[str]]:
        """Register a new organization and assign the founding user the ORG_ADMIN role."""
        # 1. Validate password strength
        is_valid, err_msg = validate_password_strength(password)
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)

        # 2. Check if email already exists
        email_clean = email.lower().strip()
        existing_user_stmt = select(User).where(User.email == email_clean)
        if (await db.execute(existing_user_stmt)).scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email address is already registered.",
            )

        # 3. Resolve organization slug
        slug = (organization_slug or re.sub(r"[^a-z0-9]+", "-", organization_name.lower()).strip("-"))
        if not slug:
            slug = f"org-{uuid.uuid4().hex[:8]}"

        existing_org_stmt = select(Organization).where(Organization.slug == slug)
        if (await db.execute(existing_org_stmt)).scalar_one_or_none():
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        # 4. Create Organization
        org = Organization(
            name=organization_name.strip(),
            slug=slug,
            domain=domain.lower().strip() if domain else None,
            is_active=True,
        )
        db.add(org)
        await db.flush()

        # 5. Create User
        pw_hash = hash_password(password)
        user = User(
            email=email_clean,
            password_hash=pw_hash,
            full_name=full_name.strip(),
            organization_id=org.id,
            is_active=True,
            is_verified=True,  # Self-registered org admin starts verified
            last_login_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()

        # 6. Ensure RBAC roles exist and assign ORG_ADMIN
        await RBACService.ensure_system_roles_and_permissions(db)
        admin_role_stmt = select(Role).where(Role.name == "ORG_ADMIN")
        admin_role = (await db.execute(admin_role_stmt)).scalar_one()

        user_role = UserRole(
            user_id=user.id,
            role_id=admin_role.id,
            organization_id=org.id,
        )
        db.add(user_role)
        await db.flush()

        # 7. Issue Session Tokens
        roles, permissions = await RBACService.get_user_roles_and_permissions(user.id, db)
        access_token = create_access_token(
            subject=str(user.id),
            org_id=str(org.id),
            roles=roles,
            permissions=permissions,
        )

        raw_refresh_token, _ = await cls._create_refresh_token(user.id, db)

        # 8. Audit Log
        audit = AuditLog(
            organization_id=org.id,
            user_id=user.id,
            action="AUTH_REGISTER",
            target_type="User",
            target_id=str(user.id),
            ip_address=ip_address,
            user_agent=user_agent,
            diff_json={"email": email_clean, "organization_slug": slug, "assigned_role": "ORG_ADMIN"},
        )
        db.add(audit)
        await db.commit()

        return access_token, raw_refresh_token, user, org, roles, permissions

    @classmethod
    async def authenticate_user(
        cls,
        email: str,
        password: str,
        db: AsyncSession,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[str, str, User, Organization, List[str], List[str]]:
        """Verify user credentials in constant time and generate access and rotating refresh tokens."""
        await cls._enable_auth_lookup(db)
        email_clean = email.lower().strip()
        stmt = (
            select(User)
            .where(User.email == email_clean)
            .options(selectinload(User.organization))
        )
        user = (await db.execute(stmt)).scalar_one_or_none()

        # Constant time verification check
        if not user or not verify_password(password, user.password_hash):
            if user and user.organization_id:
                await cls._enable_auth_lookup(db, org_id=user.organization_id)
            audit = AuditLog(
                organization_id=user.organization_id if user else None,
                user_id=user.id if user else None,
                action="AUTH_LOGIN_FAILED",
                target_type="User",
                target_id=email_clean,
                ip_address=ip_address,
                user_agent=user_agent,
                diff_json={"reason": "Invalid credentials", "email": email_clean},
            )
            db.add(audit)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated. Contact your organization administrator.",
            )

        if user.organization and not user.organization.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization subscription or account is inactive.",
            )

        # Update last login
        now = datetime.now(timezone.utc)
        user.last_login_at = now

        # Resolve roles & permissions
        roles, permissions = await RBACService.get_user_roles_and_permissions(user.id, db)
        access_token = create_access_token(
            subject=str(user.id),
            org_id=str(user.organization_id),
            roles=roles,
            permissions=permissions,
        )

        raw_refresh_token, _ = await cls._create_refresh_token(user.id, db)

        # Audit login success
        await cls._enable_auth_lookup(db, org_id=user.organization_id)
        audit = AuditLog(
            organization_id=user.organization_id,
            user_id=user.id,
            action="AUTH_LOGIN_SUCCESS",
            target_type="User",
            target_id=str(user.id),
            ip_address=ip_address,
            user_agent=user_agent,
            diff_json={"email": email_clean},
        )
        db.add(audit)
        await db.commit()

        return access_token, raw_refresh_token, user, user.organization, roles, permissions

    @classmethod
    async def rotate_refresh_token(
        cls,
        raw_refresh_token: str,
        db: AsyncSession,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[str, str, User, Organization, List[str], List[str]]:
        """Atomically rotate refresh token with concurrency-safe conditional update & reuse detection."""
        if not raw_refresh_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required.")

        await cls._enable_auth_lookup(db)
        token_hash = hash_token(raw_refresh_token)
        now = datetime.now(timezone.utc)

        # Atomic conditional update (F-05 Fix): only ONE concurrent request can claim revoked_at IS NULL
        claim_stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        claim_result = await db.execute(claim_stmt)

        stmt = (
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .options(
                selectinload(RefreshToken.user).selectinload(User.organization)
            )
        )
        token_record = (await db.execute(stmt)).scalar_one_or_none()

        if not token_record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token.",
            )

        # If rowcount == 0, token was ALREADY revoked -> Reuse detected (or lost concurrency race)!
        if claim_result.rowcount == 0:
            revoke_stmt = (
                update(RefreshToken)
                .where(RefreshToken.token_family_id == token_record.token_family_id)
                .values(revoked_at=now)
            )
            await db.execute(revoke_stmt)

            if token_record.user and token_record.user.organization_id:
                await cls._enable_auth_lookup(db, org_id=token_record.user.organization_id)
            audit = AuditLog(
                organization_id=token_record.user.organization_id if token_record.user else None,
                user_id=token_record.user_id,
                action="REFRESH_TOKEN_REUSE_DETECTED",
                target_type="RefreshToken",
                target_id=str(token_record.id),
                ip_address=ip_address,
                user_agent=user_agent,
                diff_json={"family_id": str(token_record.token_family_id), "revoked_count": "all"},
            )
            db.add(audit)
            await db.commit()

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Security violation: Refresh token reuse detected. Session terminated for security.",
            )

        # Check expiration
        expires_at = token_record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired. Please log in again.",
            )

        user = token_record.user
        if not user or not user.is_active:
            await db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive.")

        if user.organization and not user.organization.is_active:
            await db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization is inactive.")

        # Issue new token under SAME family
        new_raw_token, new_token_record = await cls._create_refresh_token(
            user.id, db, family_id=token_record.token_family_id
        )
        token_record.replaced_by_token_id = new_token_record.id

        # Issue fresh access token
        roles, permissions = await RBACService.get_user_roles_and_permissions(user.id, db)
        access_token = create_access_token(
            subject=str(user.id),
            org_id=str(user.organization_id),
            roles=roles,
            permissions=permissions,
        )

        await db.commit()
        return access_token, new_raw_token, user, user.organization, roles, permissions

    @classmethod
    async def revoke_session(
        cls,
        raw_refresh_token: Optional[str],
        db: AsyncSession,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Revoke active refresh token family upon user logout."""
        if not raw_refresh_token:
            return

        await cls._enable_auth_lookup(db)
        token_hash = hash_token(raw_refresh_token)
        stmt = (
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .options(selectinload(RefreshToken.user))
        )
        token_record = (await db.execute(stmt)).scalar_one_or_none()

        if token_record:
            now = datetime.now(timezone.utc)
            revoke_stmt = (
                update(RefreshToken)
                .where(RefreshToken.token_family_id == token_record.token_family_id)
                .values(revoked_at=now)
            )
            await db.execute(revoke_stmt)

            if token_record.user and token_record.user.organization_id:
                await cls._enable_auth_lookup(db, org_id=token_record.user.organization_id)
            audit = AuditLog(
                organization_id=token_record.user.organization_id if token_record.user else None,
                user_id=token_record.user_id,
                action="AUTH_LOGOUT",
                target_type="RefreshToken",
                target_id=str(token_record.id),
                ip_address=ip_address,
                user_agent=user_agent,
                diff_json={"family_id": str(token_record.token_family_id)},
            )
            db.add(audit)
            await db.commit()

    @classmethod
    async def _create_refresh_token(
        cls, user_id: UUID, db: AsyncSession, family_id: Optional[UUID] = None
    ) -> Tuple[str, RefreshToken]:
        """Internal helper to create a hashed refresh token entity."""
        raw_token = generate_secure_token(48)
        hashed = hash_token(raw_token)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        record = RefreshToken(
            user_id=user_id,
            token_hash=hashed,
            token_family_id=family_id or uuid.uuid4(),
            expires_at=expires,
            revoked_at=None,
            replaced_by_token_id=None,
        )
        db.add(record)
        await db.flush()
        return raw_token, record

    @classmethod
    async def create_invitation(
        cls,
        organization_id: UUID,
        email: str,
        role_name: str,
        invited_by: User,
        db: AsyncSession,
        expires_hours: int = 48,
    ) -> Tuple[str, OrganizationInvitation]:
        """Create an expiring, single-use organization invitation (F-09)."""
        if role_name == "SUPER_ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot invite SUPER_ADMIN via organization invitation.",
            )

        await RBACService.ensure_system_roles_and_permissions(db)
        role_stmt = select(Role).where(Role.name == role_name)
        role_obj = (await db.execute(role_stmt)).scalar_one_or_none()
        if not role_obj:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid role '{role_name}'.")

        raw_token = generate_secure_token(32)
        now = datetime.now(timezone.utc)
        inv = OrganizationInvitation(
            organization_id=organization_id,
            email=email.lower().strip(),
            role_name=role_name,
            token_hash=hash_token(raw_token),
            expires_at=now + timedelta(hours=expires_hours),
            invited_by_user_id=invited_by.id,
        )
        db.add(inv)
        db.add(
            AuditLog(
                organization_id=organization_id,
                user_id=invited_by.id,
                action="AUTH_INVITATION_CREATED",
                target_type="OrganizationInvitation",
                target_id=email.lower().strip(),
                diff_json={"role_name": role_name, "expires_hours": expires_hours},
            )
        )
        await db.commit()
        await db.refresh(inv)
        return raw_token, inv

    @classmethod
    async def accept_invitation(
        cls,
        invitation_token: str,
        email: str,
        password: str,
        full_name: str,
        db: AsyncSession,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[str, str, User, Organization, List[str], List[str]]:
        """Accept a single-use organization invitation and create a scoped user account."""
        is_valid, err_msg = validate_password_strength(password)
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)

        email_clean = email.lower().strip()
        token_hash = hash_token(invitation_token)
        now = datetime.now(timezone.utc)

        # Atomic single-use claim
        claim_stmt = (
            update(OrganizationInvitation)
            .where(
                OrganizationInvitation.token_hash == token_hash,
                OrganizationInvitation.email == email_clean,
                OrganizationInvitation.accepted_at.is_(None),
            )
            .values(accepted_at=now)
        )
        claim_res = await db.execute(claim_stmt)
        if claim_res.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid, expired, or already-used invitation token.",
            )

        inv_stmt = select(OrganizationInvitation).where(OrganizationInvitation.token_hash == token_hash)
        inv = (await db.execute(inv_stmt)).scalar_one()
        expires_at = inv.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation token has expired.")

        existing_user = (await db.execute(select(User).where(User.email == email_clean))).scalar_one_or_none()
        if existing_user:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered.")

        org = (await db.execute(select(Organization).where(Organization.id == inv.organization_id))).scalar_one()
        user = User(
            email=email_clean,
            password_hash=hash_password(password),
            full_name=full_name.strip(),
            organization_id=org.id,
            is_active=True,
            is_verified=True,
            last_login_at=now,
        )
        db.add(user)
        await db.flush()

        role_obj = (await db.execute(select(Role).where(Role.name == inv.role_name))).scalar_one()
        db.add(UserRole(user_id=user.id, role_id=role_obj.id, organization_id=org.id))
        await db.flush()

        roles, permissions = await RBACService.get_user_roles_and_permissions(user.id, db)
        access_token = create_access_token(
            subject=str(user.id),
            org_id=str(org.id),
            roles=roles,
            permissions=permissions,
        )
        raw_refresh_token, _ = await cls._create_refresh_token(user.id, db)

        db.add(
            AuditLog(
                organization_id=org.id,
                user_id=user.id,
                action="AUTH_INVITATION_ACCEPTED",
                target_type="User",
                target_id=str(user.id),
                ip_address=ip_address,
                user_agent=user_agent,
                diff_json={"email": email_clean, "assigned_role": inv.role_name},
            )
        )
        await db.commit()
        return access_token, raw_refresh_token, user, org, roles, permissions
