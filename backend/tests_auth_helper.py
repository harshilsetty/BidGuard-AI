"""Isolated authentication & database test helpers for Phase 1.0.3 API compatibility.

- Never modifies backend/gem_compliance.db.
- Never weakens production authentication or adds anonymous bypasses.
- Provisions isolated per-test Organization, User, and PROCUREMENT_OFFICER JWT.
"""
import os
import tempfile
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.models.organization import Organization
from app.models.rbac import Role, UserRole
from app.models.user import User
from app.services.rbac_service import RBACService


async def create_test_officer_and_headers(
    session: AsyncSession,
    role_name: str = "PROCUREMENT_OFFICER",
) -> Tuple[Organization, User, Dict[str, str]]:
    """Create an isolated organization, user, and real Bearer token headers."""
    await RBACService.ensure_system_roles_and_permissions(session)

    suffix = uuid.uuid4().hex[:8]
    org = Organization(
        id=uuid.uuid4(),
        name=f"Test Org {suffix}",
        slug=f"test-org-{suffix}",
        is_active=True,
    )
    session.add(org)
    await session.flush()

    user = User(
        id=uuid.uuid4(),
        email=f"test_{role_name.lower()}_{suffix}@test.local",
        password_hash=hash_password("TestSuitePass123!"),
        full_name=f"Test {role_name}",
        organization_id=org.id,
        is_active=True,
        is_verified=True,
    )
    session.add(user)
    await session.flush()

    role = (await session.execute(select(Role).where(Role.name == role_name))).scalar_one()
    session.add(UserRole(user_id=user.id, role_id=role.id, organization_id=org.id))
    await session.flush()

    roles, perms = await RBACService.get_user_roles_and_permissions(user.id, session)
    token = create_access_token(str(user.id), str(org.id), roles, perms)
    return org, user, {"Authorization": f"Bearer {token}"}


@asynccontextmanager
async def isolated_db_context() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Provide an isolated temporary SQLite DB and override FastAPI get_db."""
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_db.name}", echo=False, future=True)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with SessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield SessionLocal
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()
        try:
            os.remove(tmp_db.name)
        except OSError:
            pass


def yield_sync_isolated_sqlite():
    """Sync generator helper for autouse pytest fixtures supporting both sync and async tests."""
    import asyncio
    from app.core import database as db_module

    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_db.name}", echo=False, future=True)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init())

    orig_sl, orig_init = db_module.AsyncSessionLocal, db_module.init_db

    async def _noop():
        return None

    async def _get_db():
        async with SessionLocal() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    db_module.AsyncSessionLocal = SessionLocal
    db_module.init_db = _noop
    app.dependency_overrides[get_db] = _get_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)
        db_module.AsyncSessionLocal = orig_sl
        db_module.init_db = orig_init
        asyncio.run(engine.dispose())
        try:
            os.remove(tmp_db.name)
        except OSError:
            pass


@asynccontextmanager
async def patch_db_module_with_isolated_sqlite() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Patch app.core.database.init_db & AsyncSessionLocal + get_db to use an isolated temp SQLite DB."""
    from app.core import database as db_module

    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_db.name}", echo=False, future=True)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    orig_session_local = db_module.AsyncSessionLocal
    orig_init_db = db_module.init_db

    async def noop_init_db():
        return None

    async def override_get_db():
        async with SessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    db_module.AsyncSessionLocal = SessionLocal
    db_module.init_db = noop_init_db
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield SessionLocal
    finally:
        app.dependency_overrides.pop(get_db, None)
        db_module.AsyncSessionLocal = orig_session_local
        db_module.init_db = orig_init_db
        await engine.dispose()
        try:
            os.remove(tmp_db.name)
        except OSError:
            pass


def yield_sync_isolated_sqlite():
    """Sync generator helper for autouse pytest fixtures supporting both sync and async tests."""
    import asyncio
    from app.core import database as db_module

    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_db.name}", echo=False, future=True)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init())

    orig_sl, orig_init = db_module.AsyncSessionLocal, db_module.init_db

    async def _noop():
        return None

    async def _get_db():
        async with SessionLocal() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    db_module.AsyncSessionLocal = SessionLocal
    db_module.init_db = _noop
    app.dependency_overrides[get_db] = _get_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)
        db_module.AsyncSessionLocal = orig_sl
        db_module.init_db = orig_init
        asyncio.run(engine.dispose())
        try:
            os.remove(tmp_db.name)
        except OSError:
            pass
