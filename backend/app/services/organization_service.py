from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import generate_secure_token, hash_token
from app.models.audit import AuditLog
from app.models.auth import OrganizationInvitation, RefreshToken
from app.models.organization import Organization
from app.models.rbac import Role, UserRole
from app.models.user import User
from app.services.rbac_service import ROLE_PERMISSIONS_MAP, SYSTEM_ROLES, RBACService


def compute_invitation_status(inv: OrganizationInvitation, now: Optional[datetime] = None) -> str:
    """Derive canonical invitation lifecycle state."""
    current_time = now or datetime.now(timezone.utc)
    if inv.revoked_at is not None:
        return "REVOKED"
    if inv.accepted_at is not None:
        return "ACCEPTED"
    expires_at = inv.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < current_time:
        return "EXPIRED"
    return "PENDING"


class OrganizationService:
    """Service for organization profile, member management, and invitation lifecycle."""

    @classmethod
    async def get_organization_overview(
        cls, organization_id: UUID, db: AsyncSession
    ) -> dict:
        org = (
            await db.execute(select(Organization).where(Organization.id == organization_id))
        ).scalar_one_or_none()
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

        total_members = (
            await db.execute(
                select(func.count(User.id)).where(User.organization_id == organization_id)
            )
        ).scalar() or 0

        active_members = (
            await db.execute(
                select(func.count(User.id)).where(
                    User.organization_id == organization_id,
                    User.is_active.is_(True),
                )
            )
        ).scalar() or 0

        now = datetime.now(timezone.utc)
        pending_invitations = (
            await db.execute(
                select(func.count(OrganizationInvitation.id)).where(
                    OrganizationInvitation.organization_id == organization_id,
                    OrganizationInvitation.accepted_at.is_(None),
                    OrganizationInvitation.revoked_at.is_(None),
                    OrganizationInvitation.expires_at > now,
                )
            )
        ).scalar() or 0

        return {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "domain": org.domain,
            "is_active": org.is_active,
            "created_at": org.created_at,
            "updated_at": org.updated_at,
            "total_members": total_members,
            "active_members": active_members,
            "pending_invitations": pending_invitations,
        }

    @classmethod
    async def update_organization_profile(
        cls,
        organization_id: UUID,
        actor: User,
        name: Optional[str],
        domain: Optional[str],
        domain_provided: bool,
        db: AsyncSession,
    ) -> dict:
        org = (
            await db.execute(select(Organization).where(Organization.id == organization_id))
        ).scalar_one_or_none()
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

        changes = {}
        if name is not None and name != org.name:
            changes["name"] = {"from": org.name, "to": name}
            org.name = name
        if domain_provided and domain != org.domain:
            changes["domain"] = {"from": org.domain, "to": domain}
            org.domain = domain

        if changes:
            db.add(
                AuditLog(
                    organization_id=organization_id,
                    user_id=actor.id,
                    action="ORGANIZATION_PROFILE_UPDATED",
                    target_type="Organization",
                    target_id=str(organization_id),
                    diff_json=changes,
                )
            )
            await db.commit()
            await db.refresh(org)

        return await cls.get_organization_overview(organization_id, db)

    @classmethod
    def list_role_summaries(cls) -> List[dict]:
        """Return system roles and their permissions, flagging org-admin assignability."""
        items = []
        for role_name, desc in SYSTEM_ROLES.items():
            items.append(
                {
                    "name": role_name,
                    "description": desc,
                    "scope": "PLATFORM" if role_name == "SUPER_ADMIN" else "ORGANIZATION",
                    "assignable_by_org_admin": role_name != "SUPER_ADMIN",
                    "permissions": ROLE_PERMISSIONS_MAP.get(role_name, []),
                }
            )
        return items

    @classmethod
    async def list_members(
        cls,
        organization_id: UUID,
        db: AsyncSession,
        q: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> Tuple[List[dict], int]:
        filters = [User.organization_id == organization_id]
        if q and q.strip():
            term = f"%{q.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(User.email).like(term),
                    func.lower(User.full_name).like(term),
                )
            )
        if is_active is not None:
            filters.append(User.is_active.is_(is_active))
        if role and role.strip():
            role_subq = (
                select(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(
                    UserRole.organization_id == organization_id,
                    Role.name == role.strip(),
                )
            )
            filters.append(User.id.in_(role_subq))

        total = (
            await db.execute(select(func.count(User.id)).where(and_(*filters)))
        ).scalar() or 0

        stmt = (
            select(User)
            .where(and_(*filters))
            .options(selectinload(User.user_roles).selectinload(UserRole.role))
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        users = (await db.execute(stmt)).scalars().all()

        items = []
        for u in users:
            role_names = sorted({ur.role.name for ur in u.user_roles if ur.role})
            items.append(
                {
                    "id": u.id,
                    "email": u.email,
                    "full_name": u.full_name,
                    "organization_id": u.organization_id,
                    "roles": role_names,
                    "is_active": u.is_active,
                    "is_verified": u.is_verified,
                    "last_login_at": u.last_login_at,
                    "created_at": u.created_at,
                }
            )
        return items, total

    @classmethod
    async def _count_active_org_admins(cls, organization_id: UUID, db: AsyncSession) -> int:
        stmt = (
            select(func.count(func.distinct(User.id)))
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                User.organization_id == organization_id,
                User.is_active.is_(True),
                Role.name == "ORG_ADMIN",
            )
        )
        return (await db.execute(stmt)).scalar() or 0

    @classmethod
    async def _get_org_member_or_404(
        cls, organization_id: UUID, target_user_id: UUID, db: AsyncSession
    ) -> User:
        stmt = (
            select(User)
            .where(User.id == target_user_id, User.organization_id == organization_id)
            .options(selectinload(User.user_roles).selectinload(UserRole.role))
            .execution_options(populate_existing=True)
        )
        target = (await db.execute(stmt)).scalar_one_or_none()
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization member not found.")
        return target

    @classmethod
    async def update_member_role(
        cls,
        organization_id: UUID,
        target_user_id: UUID,
        role_name: str,
        actor: User,
        db: AsyncSession,
    ) -> dict:
        if target_user_id == actor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Self-role modification is forbidden.",
            )

        if role_name == "SUPER_ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot assign SUPER_ADMIN at organization level.",
            )

        await RBACService.ensure_system_roles_and_permissions(db)
        new_role = (await db.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
        if not new_role:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid role '{role_name}'.")

        target = await cls._get_org_member_or_404(organization_id, target_user_id, db)
        current_roles = sorted({ur.role.name for ur in target.user_roles if ur.role})

        if "SUPER_ADMIN" in current_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify a platform SUPER_ADMIN account.",
            )

        if "ORG_ADMIN" in current_roles and role_name != "ORG_ADMIN" and target.is_active:
            admin_count = await cls._count_active_org_admins(organization_id, db)
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot demote the last active organization administrator.",
                )

        await db.execute(delete(UserRole).where(UserRole.user_id == target.id))
        db.add(UserRole(user_id=target.id, role_id=new_role.id, organization_id=organization_id))
        db.add(
            AuditLog(
                organization_id=organization_id,
                user_id=actor.id,
                action="MEMBER_ROLE_UPDATED",
                target_type="User",
                target_id=str(target.id),
                diff_json={"previous_roles": current_roles, "new_role": role_name},
            )
        )
        await db.commit()

        refreshed = await cls._get_org_member_or_404(organization_id, target.id, db)
        return {
            "id": refreshed.id,
            "email": refreshed.email,
            "full_name": refreshed.full_name,
            "organization_id": refreshed.organization_id,
            "roles": sorted({ur.role.name for ur in refreshed.user_roles if ur.role}),
            "is_active": refreshed.is_active,
            "is_verified": refreshed.is_verified,
            "last_login_at": refreshed.last_login_at,
            "created_at": refreshed.created_at,
        }

    @classmethod
    async def update_member_status(
        cls,
        organization_id: UUID,
        target_user_id: UUID,
        is_active: bool,
        actor: User,
        db: AsyncSession,
    ) -> dict:
        if target_user_id == actor.id and not is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot deactivate your own administrator account.",
            )

        target = await cls._get_org_member_or_404(organization_id, target_user_id, db)
        current_roles = sorted({ur.role.name for ur in target.user_roles if ur.role})

        if "SUPER_ADMIN" in current_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify a platform SUPER_ADMIN account.",
            )

        if not is_active and "ORG_ADMIN" in current_roles and target.is_active:
            admin_count = await cls._count_active_org_admins(organization_id, db)
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot deactivate the last active organization administrator.",
                )

        previous_status = target.is_active
        target.is_active = is_active

        if not is_active:
            now = datetime.now(timezone.utc)
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == target.id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=now)
            )

        db.add(
            AuditLog(
                organization_id=organization_id,
                user_id=actor.id,
                action="MEMBER_STATUS_UPDATED",
                target_type="User",
                target_id=str(target.id),
                diff_json={"from": previous_status, "to": is_active},
            )
        )
        await db.commit()

        return {
            "id": target.id,
            "email": target.email,
            "full_name": target.full_name,
            "organization_id": target.organization_id,
            "roles": current_roles,
            "is_active": target.is_active,
            "is_verified": target.is_verified,
            "last_login_at": target.last_login_at,
            "created_at": target.created_at,
        }

    @classmethod
    async def remove_member(
        cls,
        organization_id: UUID,
        target_user_id: UUID,
        actor: User,
        db: AsyncSession,
    ) -> None:
        if target_user_id == actor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot remove your own administrator account.",
            )

        target = await cls._get_org_member_or_404(organization_id, target_user_id, db)
        current_roles = sorted({ur.role.name for ur in target.user_roles if ur.role})

        if "SUPER_ADMIN" in current_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot remove a platform SUPER_ADMIN account.",
            )

        if "ORG_ADMIN" in current_roles and target.is_active:
            admin_count = await cls._count_active_org_admins(organization_id, db)
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot remove the last active organization administrator.",
                )

        db.add(
            AuditLog(
                organization_id=organization_id,
                user_id=actor.id,
                action="MEMBER_REMOVED",
                target_type="User",
                target_id=str(target.id),
                diff_json={"email": target.email, "roles": current_roles},
            )
        )
        await db.delete(target)
        await db.commit()

    @classmethod
    async def list_invitations(
        cls,
        organization_id: UUID,
        db: AsyncSession,
        status_filter: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> Tuple[List[dict], int]:
        now = datetime.now(timezone.utc)
        filters = [OrganizationInvitation.organization_id == organization_id]

        if status_filter:
            sf = status_filter.strip().upper()
            if sf == "REVOKED":
                filters.append(OrganizationInvitation.revoked_at.is_not(None))
            elif sf == "ACCEPTED":
                filters.append(
                    and_(
                        OrganizationInvitation.revoked_at.is_(None),
                        OrganizationInvitation.accepted_at.is_not(None),
                    )
                )
            elif sf == "EXPIRED":
                filters.append(
                    and_(
                        OrganizationInvitation.revoked_at.is_(None),
                        OrganizationInvitation.accepted_at.is_(None),
                        OrganizationInvitation.expires_at < now,
                    )
                )
            elif sf == "PENDING":
                filters.append(
                    and_(
                        OrganizationInvitation.revoked_at.is_(None),
                        OrganizationInvitation.accepted_at.is_(None),
                        OrganizationInvitation.expires_at >= now,
                    )
                )

        total = (
            await db.execute(select(func.count(OrganizationInvitation.id)).where(and_(*filters)))
        ).scalar() or 0

        stmt = (
            select(OrganizationInvitation)
            .where(and_(*filters))
            .order_by(OrganizationInvitation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await db.execute(stmt)).scalars().all()

        items = [
            {
                "id": inv.id,
                "organization_id": inv.organization_id,
                "email": inv.email,
                "role_name": inv.role_name,
                "status": compute_invitation_status(inv, now),
                "expires_at": inv.expires_at,
                "accepted_at": inv.accepted_at,
                "revoked_at": inv.revoked_at,
                "invited_by_user_id": inv.invited_by_user_id,
                "created_at": inv.created_at,
            }
            for inv in rows
        ]
        return items, total

    @classmethod
    async def revoke_invitation(
        cls,
        organization_id: UUID,
        invitation_id: UUID,
        actor: User,
        db: AsyncSession,
    ) -> dict:
        inv = (
            await db.execute(
                select(OrganizationInvitation).where(
                    OrganizationInvitation.id == invitation_id,
                    OrganizationInvitation.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        if not inv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")

        if inv.accepted_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot revoke an already accepted invitation.")
        if inv.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation is already revoked.")

        now = datetime.now(timezone.utc)
        inv.revoked_at = now
        db.add(
            AuditLog(
                organization_id=organization_id,
                user_id=actor.id,
                action="AUTH_INVITATION_REVOKED",
                target_type="OrganizationInvitation",
                target_id=str(inv.id),
                diff_json={"email": inv.email, "role_name": inv.role_name},
            )
        )
        await db.commit()
        await db.refresh(inv)

        return {
            "id": inv.id,
            "organization_id": inv.organization_id,
            "email": inv.email,
            "role_name": inv.role_name,
            "status": compute_invitation_status(inv, now),
            "expires_at": inv.expires_at,
            "accepted_at": inv.accepted_at,
            "revoked_at": inv.revoked_at,
            "invited_by_user_id": inv.invited_by_user_id,
            "created_at": inv.created_at,
        }

    @classmethod
    async def resend_invitation(
        cls,
        organization_id: UUID,
        invitation_id: UUID,
        actor: User,
        db: AsyncSession,
        expires_hours: int = 48,
    ) -> Tuple[str, OrganizationInvitation]:
        """Revoke an existing non-accepted invitation and issue a fresh single-use token."""
        inv = (
            await db.execute(
                select(OrganizationInvitation).where(
                    OrganizationInvitation.id == invitation_id,
                    OrganizationInvitation.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        if not inv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")

        if inv.accepted_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot resend an already accepted invitation.")

        now = datetime.now(timezone.utc)
        if inv.revoked_at is None:
            inv.revoked_at = now

        raw_token = generate_secure_token(32)
        new_inv = OrganizationInvitation(
            organization_id=organization_id,
            email=inv.email,
            role_name=inv.role_name,
            token_hash=hash_token(raw_token),
            expires_at=now + timedelta(hours=expires_hours),
            invited_by_user_id=actor.id,
        )
        db.add(new_inv)
        db.add(
            AuditLog(
                organization_id=organization_id,
                user_id=actor.id,
                action="AUTH_INVITATION_RESENT",
                target_type="OrganizationInvitation",
                target_id=inv.email,
                diff_json={"previous_invitation_id": str(inv.id), "role_name": inv.role_name},
            )
        )
        await db.commit()
        await db.refresh(new_inv)
        return raw_token, new_inv
