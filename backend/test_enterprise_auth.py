import os
import uuid
from typing import AsyncGenerator
import pytest
import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import hash_password, verify_password
from app.services.rbac_service import RBACService

TEST_DB_PATH = "test_enterprise_auth.db"
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def setup_test_database(monkeypatch):
    from app.core.config import settings
    from app.api.v1.auth import reset_auth_rate_limiter
    reset_auth_rate_limiter()
    monkeypatch.setattr(settings, "ALLOW_PUBLIC_ORG_SIGNUP", True)
    app.dependency_overrides[get_db] = override_get_db
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed RBAC
    async with TestSessionLocal() as session:
        await RBACService.ensure_system_roles_and_permissions(session)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    app.dependency_overrides.pop(get_db, None)
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass


@pytest.fixture
async def async_client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.anyio
async def test_password_hashing_argon2id():
    """Verify password hashing strictly uses Argon2id and never plaintext."""
    pwd = "EnterpriseSecurePass123!"
    hashed = hash_password(pwd)
    assert hashed.startswith("$argon2id$"), "Hash must be in Argon2id format"
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


@pytest.mark.anyio
async def test_auth_registration_and_login_flow(async_client: httpx.AsyncClient):
    """Verify full enterprise registration, login, token issuance, and me endpoint."""
    unique_suffix = uuid.uuid4().hex[:6]
    email = f"officer_{unique_suffix}@gem-procurement.gov.in"
    password = "StrongPassword2026!"
    org_name = f"Defense Procurement Directorate {unique_suffix}"

    # 1. Weak password rejected by validator (HTTP 422)
    weak_resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "weak",
            "full_name": "Test Officer",
            "organization_name": org_name,
        },
    )
    assert weak_resp.status_code in [400, 422]

    # 2. Successful Registration
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Major General Sharma",
            "organization_name": org_name,
        },
    )
    assert reg_resp.status_code == 201
    reg_data = reg_resp.json()
    assert "access_token" in reg_data
    assert "ORG_ADMIN" in reg_data["roles"]
    assert "tender:create" in reg_data["permissions"]
    access_token = reg_data["access_token"]

    # Verify refresh cookie was set
    assert "bidguard_refresh_token" in reg_resp.cookies

    # 3. Duplicate email rejected
    dup_resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Duplicate User",
            "organization_name": "Another Org",
        },
    )
    assert dup_resp.status_code == 409

    # 4. Successful Login
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    new_access_token = login_data["access_token"]
    assert "bidguard_refresh_token" in login_resp.cookies

    # 5. Invalid credentials rejected
    bad_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword2026!"},
    )
    assert bad_login.status_code == 401
    assert "Invalid email or password" in bad_login.json()["detail"]

    # 6. Access /me endpoint with valid token
    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {new_access_token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == email
    assert me_data["full_name"] == "Major General Sharma"
    assert "ORG_ADMIN" in me_data["roles"]
    assert me_data["is_active"] is True


@pytest.mark.anyio
async def test_refresh_token_rotation_and_reuse_detection(async_client: httpx.AsyncClient):
    """Verify refresh token rotation and adversarial reuse detection."""
    unique_suffix = uuid.uuid4().hex[:6]
    email = f"reuse_test_{unique_suffix}@gem.gov.in"
    password = "SecurePassword2026!"

    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Session Tester",
            "organization_name": f"Session Org {unique_suffix}",
        },
    )
    assert reg_resp.status_code == 201
    token1 = reg_resp.cookies["bidguard_refresh_token"]

    # First rotation: use token1 -> receives token2
    rot1_resp = await async_client.post(
        "/api/v1/auth/refresh",
        cookies={"bidguard_refresh_token": token1},
    )
    assert rot1_resp.status_code == 200
    token2 = rot1_resp.cookies["bidguard_refresh_token"]
    assert token2 != token1

    # REUSE ATTACK: Presenting token1 again must trigger reuse detection!
    reuse_resp = await async_client.post(
        "/api/v1/auth/refresh",
        cookies={"bidguard_refresh_token": token1},
    )
    assert reuse_resp.status_code == 401
    assert "reuse detected" in reuse_resp.json()["detail"].lower()

    # Verify that the entire family (including token2) was revoked by the reuse trigger
    rot2_resp = await async_client.post(
        "/api/v1/auth/refresh",
        cookies={"bidguard_refresh_token": token2},
    )
    assert rot2_resp.status_code == 401


@pytest.mark.anyio
async def test_logout_session_invalidation(async_client: httpx.AsyncClient):
    """Verify logout invalidates refresh token and clears cookie."""
    unique_suffix = uuid.uuid4().hex[:6]
    email = f"logout_{unique_suffix}@gem.gov.in"
    password = "LogoutPassword2026!"

    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Logout Tester",
            "organization_name": f"Logout Org {unique_suffix}",
        },
    )
    assert reg_resp.status_code == 201
    refresh_token = reg_resp.cookies["bidguard_refresh_token"]

    # Logout
    logout_resp = await async_client.post(
        "/api/v1/auth/logout",
        cookies={"bidguard_refresh_token": refresh_token},
    )
    assert logout_resp.status_code == 200

    # Attempting to refresh with logged-out token fails
    refresh_after_logout = await async_client.post(
        "/api/v1/auth/refresh",
        cookies={"bidguard_refresh_token": refresh_token},
    )
    assert refresh_after_logout.status_code == 401
