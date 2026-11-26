import logging
from typing import Dict, List, Set, Tuple
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.rbac import Role, Permission, RolePermission, UserRole

logger = logging.getLogger(__name__)

SYSTEM_ROLES = {
    "SUPER_ADMIN": "Platform-level administrator with full cross-tenant governance.",
    "ORG_ADMIN": "Organization administrator managing users, roles, and settings.",
    "PROCUREMENT_OFFICER": "Procurement officer managing tenders, evaluations, and compliance reviews.",
    "AUDITOR": "Read-only auditor with comprehensive verification and log inspection access.",
    "BIDDER": "Bidder representative with restricted access to own bid evaluations.",
}

SYSTEM_PERMISSIONS = {
    "organization:read": "View organization details and profile.",
    "organization:update": "Modify organization configuration and metadata.",
    "user:invite": "Invite new members to the organization.",
    "user:manage": "Update user status, activate, or deactivate members.",
    "tender:create": "Create new procurement tenders and extract clauses.",
    "tender:read": "View tenders, clauses, and general tender metadata.",
    "tender:update": "Modify tender details and clause definitions.",
    "tender:delete": "Delete unfinalized tenders.",
    "document:upload": "Upload bidder proposals and supporting documentation.",
    "document:download": "Download original bid files and extracted text.",
    "evaluation:run": "Execute compliance engines and deterministic rules.",
    "evaluation:read": "View clause evaluation results and citations.",
    "evaluation:override": "Apply officer compliance overrides and justification notes.",
    "audit:read": "Inspect security audit logs and recommendation history.",
    "audit:export": "Export signed compliance reports and immutable audit trails.",
}

ROLE_PERMISSIONS_MAP: Dict[str, List[str]] = {
    "SUPER_ADMIN": list(SYSTEM_PERMISSIONS.keys()),
    "ORG_ADMIN": [
        "organization:read", "organization:update", "user:invite", "user:manage",
        "tender:create", "tender:read", "tender:update", "document:upload",
        "document:download", "evaluation:run", "evaluation:read", "evaluation:override",
        "audit:read", "audit:export",
    ],
    "PROCUREMENT_OFFICER": [
        "organization:read", "tender:create", "tender:read", "tender:update",
        "document:upload", "document:download", "evaluation:run", "evaluation:read",
        "evaluation:override", "audit:read",
    ],
    "AUDITOR": [
        "organization:read", "tender:read", "document:download",
        "evaluation:read", "audit:read", "audit:export",
    ],
    "BIDDER": [
        "tender:read", "evaluation:read",
    ],
}


class RBACService:
    """Service managing role-based access control, permission resolution, and seeding."""

    @classmethod
    async def ensure_system_roles_and_permissions(cls, db: AsyncSession) -> None:
        """Seed all required system roles and permissions idempotently."""
        # 1. Seed Permissions
        perm_objs: Dict[str, Permission] = {}
        for perm_name, desc in SYSTEM_PERMISSIONS.items():
            stmt = select(Permission).where(Permission.name == perm_name)
            existing = (await db.execute(stmt)).scalar_one_or_none()
            if not existing:
                existing = Permission(name=perm_name, description=desc)
                db.add(existing)
                await db.flush()
            perm_objs[perm_name] = existing

        # 2. Seed Roles
        role_objs: Dict[str, Role] = {}
        for role_name, desc in SYSTEM_ROLES.items():
            stmt = select(Role).where(Role.name == role_name)
            existing = (await db.execute(stmt)).scalar_one_or_none()
            scope = "PLATFORM" if role_name == "SUPER_ADMIN" else "ORGANIZATION"
            if not existing:
                existing = Role(name=role_name, description=desc, scope=scope)
                db.add(existing)
                await db.flush()
            role_objs[role_name] = existing

        # 3. Seed Role Permissions
        for role_name, perms in ROLE_PERMISSIONS_MAP.items():
            role_obj = role_objs[role_name]
            # Fetch existing mappings
            rp_stmt = select(RolePermission.permission_id).where(RolePermission.role_id == role_obj.id)
            existing_p_ids = set((await db.execute(rp_stmt)).scalars().all())

            for p_name in perms:
                perm_obj = perm_objs[p_name]
                if perm_obj.id not in existing_p_ids:
                    rp = RolePermission(role_id=role_obj.id, permission_id=perm_obj.id)
                    db.add(rp)

        await db.commit()

    @classmethod
    async def get_user_roles_and_permissions(
        cls, user_id: UUID, db: AsyncSession
    ) -> Tuple[List[str], List[str]]:
        """Resolve all assigned role names and distinct permission names for a user."""
        stmt = (
            select(UserRole)
            .where(UserRole.user_id == user_id)
            .options(
                selectinload(UserRole.role)
                .selectinload(Role.role_permissions)
                .selectinload(RolePermission.permission)
            )
        )
        user_roles = (await db.execute(stmt)).scalars().all()

        role_names: List[str] = []
        permissions: Set[str] = set()

        for ur in user_roles:
            if ur.role:
                role_names.append(ur.role.name)
                for rp in ur.role.role_permissions:
                    if rp.permission:
                        permissions.add(rp.permission.name)

        return sorted(list(set(role_names))), sorted(list(permissions))
