import pytest
import httpx
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.models.organization import Organization
from app.models.user import User
from app.models.rbac import Role, UserRole
from app.models.audit import AuditLog
from app.core.security import hash_password, create_access_token
from app.services.rbac_service import RBACService

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture
async def test_audit_db():
    test_engine = create_async_engine(TEST_DB_URL, echo=False, future=True)
    async_session = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield async_session
    app.dependency_overrides.clear()
    await test_engine.dispose()

@pytest.mark.anyio
async def test_audit_logs_rbac_and_tenant_isolation(test_audit_db):
    async with test_audit_db() as session:
        await RBACService.ensure_system_roles_and_permissions(session)

        # Get roles
        auditor_role = (await session.execute(select(Role).where(Role.name == "AUDITOR"))).scalar_one()
        bidder_role = (await session.execute(select(Role).where(Role.name == "BIDDER"))).scalar_one()

        # Create Org A and Org B
        org_a = Organization(id=uuid4(), name="Audit Org A", slug=f"audit-a-{uuid4().hex[:6]}")
        org_b = Organization(id=uuid4(), name="Audit Org B", slug=f"audit-b-{uuid4().hex[:6]}")
        session.add_all([org_a, org_b])
        await session.flush()

        # Users in Org A: Auditor, Bidder
        u_auditor_a = User(
            id=uuid4(),
            email=f"auditor-a-{uuid4().hex[:6]}@example.com",
            password_hash=hash_password("AuditorStrongPass123!"),
            full_name="Auditor A",
            organization_id=org_a.id,
            is_active=True,
        )
        u_bidder_a = User(
            id=uuid4(),
            email=f"bidder-a-{uuid4().hex[:6]}@example.com",
            password_hash=hash_password("BidderStrongPass123!"),
            full_name="Bidder A",
            organization_id=org_a.id,
            is_active=True,
        )
        # Auditor in Org B
        u_auditor_b = User(
            id=uuid4(),
            email=f"auditor-b-{uuid4().hex[:6]}@example.com",
            password_hash=hash_password("AuditorBPass123!"),
            full_name="Auditor B",
            organization_id=org_b.id,
            is_active=True,
        )
        session.add_all([u_auditor_a, u_bidder_a, u_auditor_b])
        await session.flush()

        ur_aud_a = UserRole(user_id=u_auditor_a.id, role_id=auditor_role.id, organization_id=org_a.id)
        ur_bid_a = UserRole(user_id=u_bidder_a.id, role_id=bidder_role.id, organization_id=org_a.id)
        ur_aud_b = UserRole(user_id=u_auditor_b.id, role_id=auditor_role.id, organization_id=org_b.id)
        session.add_all([ur_aud_a, ur_bid_a, ur_aud_b])

        # Seed audit logs
        log_a1 = AuditLog(
            id=uuid4(),
            organization_id=org_a.id,
            user_id=u_auditor_a.id,
            action="COMPLIANCE_EVALUATION_OVERRIDE",
            target_type="COMPLIANCE_EVALUATION",
            target_id=str(uuid4()),
            diff_json={"status": {"old": "FAIL", "new": "PASS"}},
        )
        log_a2 = AuditLog(
            id=uuid4(),
            organization_id=org_a.id,
            user_id=u_auditor_a.id,
            action="CLAUSE_MODIFIED",
            target_type="TENDER_CLAUSE",
            target_id=str(uuid4()),
            diff_json={"is_mandatory": {"old": False, "new": True}},
        )
        log_b1 = AuditLog(
            id=uuid4(),
            organization_id=org_b.id,
            user_id=u_auditor_b.id,
            action="TENDER_UPLOADED",
            target_type="TENDER",
            target_id=str(uuid4()),
            diff_json={"title": "Org B Secret Tender"},
        )
        session.add_all([log_a1, log_a2, log_b1])
        await session.commit()

        auditor_a_token = create_access_token(
            subject=str(u_auditor_a.id),
            org_id=str(org_a.id),
            roles=["AUDITOR"],
            permissions=["organization:read", "tender:read", "document:download", "evaluation:read", "audit:read", "audit:export"],
        )
        bidder_a_token = create_access_token(
            subject=str(u_bidder_a.id),
            org_id=str(org_a.id),
            roles=["BIDDER"],
            permissions=["tender:read", "evaluation:read"],
        )
        auditor_b_token = create_access_token(
            subject=str(u_auditor_b.id),
            org_id=str(org_b.id),
            roles=["AUDITOR"],
            permissions=["organization:read", "tender:read", "document:download", "evaluation:read", "audit:read", "audit:export"],
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unauthenticated request -> 401
        res_anon = await client.get("/api/v1/audit/logs")
        assert res_anon.status_code == 401

        # 2. Bidder (lacks audit:read) -> 403 Forbidden
        res_bidder = await client.get(
            "/api/v1/audit/logs",
            headers={"Authorization": f"Bearer {bidder_a_token}"}
        )
        assert res_bidder.status_code == 403

        # 3. Auditor Org A -> 200 OK, exactly 2 logs, none from Org B
        res_auditor_a = await client.get(
            "/api/v1/audit/logs",
            headers={"Authorization": f"Bearer {auditor_a_token}"}
        )
        assert res_auditor_a.status_code == 200
        logs_a = res_auditor_a.json()["items"]
        assert len(logs_a) == 2
        for log in logs_a:
            assert log["organization_id"] == str(org_a.id)
            assert log["action"] in ["COMPLIANCE_EVALUATION_OVERRIDE", "CLAUSE_MODIFIED"]

        # 4. Auditor Org B -> 200 OK, exactly 1 log, Org B only
        res_auditor_b = await client.get(
            "/api/v1/audit/logs",
            headers={"Authorization": f"Bearer {auditor_b_token}"}
        )
        assert res_auditor_b.status_code == 200
        logs_b = res_auditor_b.json()["items"]
        assert len(logs_b) == 1
        assert logs_b[0]["organization_id"] == str(org_b.id)
        assert logs_b[0]["action"] == "TENDER_UPLOADED"
