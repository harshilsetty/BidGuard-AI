import os
import uuid
from typing import AsyncGenerator
import pytest
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.core.database import Base, get_db
from app.core.security import hash_password, create_access_token
from app.models.organization import Organization
from app.models.user import User
from app.models.tender import Tender
from app.models.clause import TenderClause
from app.models.bidder import Bidder
from app.models.evaluation import ComplianceEvaluation
from app.models.rbac import Role, UserRole
from app.services.rbac_service import RBACService

TEST_DB_PATH = "test_enterprise_tenant_rbac.db"
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

    # Seed RBAC system roles and permissions
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
async def test_cross_tenant_isolation_adversarial(async_client: httpx.AsyncClient):
    """
    Adversarial cross-tenant test:
    - Organization A (Procurement Officer A)
    - Organization B (Procurement Officer B)
    Verify complete tenant isolation across reads, writes, and decision overrides.
    """
    # 1. Register Organization A and Organization B
    suffix = uuid.uuid4().hex[:6]
    resp_a = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"officer_a_{suffix}@org-a.gov.in",
            "password": "PasswordOrgA2026!",
            "full_name": "Officer A",
            "organization_name": f"Indian Army Procurement {suffix}",
        },
    )
    assert resp_a.status_code == 201
    data_a = resp_a.json()
    token_a = data_a["access_token"]
    org_a_id = data_a["organization_id"]

    resp_b = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"officer_b_{suffix}@org-b.gov.in",
            "password": "PasswordOrgB2026!",
            "full_name": "Officer B",
            "organization_name": f"Indian Railways Supply {suffix}",
        },
    )
    assert resp_b.status_code == 201
    data_b = resp_b.json()
    token_b = data_b["access_token"]
    org_b_id = data_b["organization_id"]

    # 2. Seed a Tender directly for Org B in database
    async with TestSessionLocal() as session:
        tender_b = Tender(
            id=uuid.uuid4(),
            organization_id=uuid.UUID(org_b_id),
            title="Railways High-Speed Rolling Stock Tender",
            gem_tender_id=f"GEM/RAIL/{suffix}",
            total_pages=5,
            extraction_status="READY",
            next_clause_seq={"TECH": 2},
        )
        clause_b = TenderClause(
            id=uuid.uuid4(),
            tender_id=tender_b.id,
            clause_code="TECH-01",
            category="TECHNICAL",
            title="Locomotive Power Specs",
            description="Minimum 6000 HP traction motors",
            source_text="Locomotives must possess at least 6000 HP.",
            is_mandatory=True,
            page_number=1,
        )
        bidder_b = Bidder(
            id=uuid.uuid4(),
            tender_id=tender_b.id,
            company_name="Bharat Heavy Power Corp",
            final_status="UNDER_REVIEW",
        )
        eval_b = ComplianceEvaluation(
            id=uuid.uuid4(),
            bidder_id=bidder_b.id,
            clause_id=clause_b.id,
            status="REVIEW",
            confidence_score=0.85,
            reasoning="Awaiting test report",
            evidence_page_number=1,
        )
        session.add_all([tender_b, clause_b, bidder_b, eval_b])
        await session.commit()
        tender_b_id = str(tender_b.id)
        eval_b_id = str(eval_b.id)

    # 3. User A lists tenders: Tender B MUST NOT appear!
    list_a_resp = await async_client.get(
        "/api/v1/tenders",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert list_a_resp.status_code == 200
    tender_ids_seen_by_a = [t["id"] for t in list_a_resp.json()]
    assert tender_b_id not in tender_ids_seen_by_a, "Tenant A must NOT see Tenant B's tenders in list!"

    # 4. User A attempts to retrieve Tender B by ID: MUST RETURN 404 NOT FOUND!
    get_b_resp = await async_client.get(
        f"/api/v1/tenders/{tender_b_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert get_b_resp.status_code == 404, "Tenant A must receive 404 when querying Tenant B's tender!"

    # 5. User A attempts to add a clause to Tender B: MUST RETURN 404 NOT FOUND!
    add_clause_resp = await async_client.post(
        f"/api/v1/tenders/{tender_b_id}/clauses",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "category": "TECHNICAL",
            "title": "Adversarial Injected Clause",
            "description": "Unauthorized injection",
            "source_text": "Injected text",
            "is_mandatory": True,
            "page_number": 1,
        },
    )
    assert add_clause_resp.status_code == 404

    # 6. User A attempts to override an evaluation on Tender B: MUST RETURN 404 NOT FOUND!
    override_resp = await async_client.post(
        f"/api/v1/tenders/{tender_b_id}/evaluations/{eval_b_id}/override",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "override_status": "PASS",
            "override_reason": "Adversarial cross-tenant override attempt",
        },
    )
    assert override_resp.status_code == 404

    # 7. User B (legitimate owner) CAN access Tender B
    legit_get = await async_client.get(
        f"/api/v1/tenders/{tender_b_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert legit_get.status_code == 200
    assert legit_get.json()["title"] == "Railways High-Speed Rolling Stock Tender"


@pytest.mark.anyio
async def test_rbac_permission_boundaries(async_client: httpx.AsyncClient):
    """
    Verify RBAC role permissions:
    - AUDITOR cannot override compliance evaluations (403 Forbidden).
    - PROCUREMENT_OFFICER can override compliance evaluations.
    """
    suffix = uuid.uuid4().hex[:6]
    # Register org
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"admin_{suffix}@defense.gov.in",
            "password": "DefensePassword2026!",
            "full_name": "Defense Admin",
            "organization_name": f"Defense Department {suffix}",
        },
    )
    assert resp.status_code == 201
    org_id = uuid.UUID(resp.json()["organization_id"])

    # Create Auditor user and Procurement Officer user in DB
    async with TestSessionLocal() as session:
        auditor_role = (await session.execute(select(Role).where(Role.name == "AUDITOR"))).scalar_one()
        officer_role = (await session.execute(select(Role).where(Role.name == "PROCUREMENT_OFFICER"))).scalar_one()

        auditor_user = User(
            id=uuid.uuid4(),
            email=f"auditor_{suffix}@defense.gov.in",
            password_hash=hash_password("AuditorPass2026!"),
            full_name="CAG Auditor Verma",
            organization_id=org_id,
            is_active=True,
            is_verified=True,
        )
        officer_user = User(
            id=uuid.uuid4(),
            email=f"officer_{suffix}@defense.gov.in",
            password_hash=hash_password("OfficerPass2026!"),
            full_name="Procurement Officer Rao",
            organization_id=org_id,
            is_active=True,
            is_verified=True,
        )
        session.add_all([auditor_user, officer_user])
        await session.flush()

        ur_auditor = UserRole(user_id=auditor_user.id, role_id=auditor_role.id, organization_id=org_id)
        ur_officer = UserRole(user_id=officer_user.id, role_id=officer_role.id, organization_id=org_id)
        session.add_all([ur_auditor, ur_officer])

        # Seed Tender and Evaluation for this org
        tender = Tender(
            id=uuid.uuid4(),
            organization_id=org_id,
            title="Naval Sonar Procurement",
            gem_tender_id=f"GEM/NAVY/{suffix}",
            total_pages=3,
            extraction_status="READY",
            next_clause_seq={"TECH": 2},
        )
        clause = TenderClause(
            id=uuid.uuid4(),
            tender_id=tender.id,
            clause_code="TECH-01",
            category="TECHNICAL",
            title="Sonar Detection Range",
            description="Minimum 25 km active detection range",
            source_text="Sonar must detect at 25 km.",
            is_mandatory=True,
            page_number=1,
        )
        bidder = Bidder(
            id=uuid.uuid4(),
            tender_id=tender.id,
            company_name="Oceanic Acoustic Systems Ltd",
            final_status="UNDER_REVIEW",
        )
        eval_item = ComplianceEvaluation(
            id=uuid.uuid4(),
            bidder_id=bidder.id,
            clause_id=clause.id,
            status="REVIEW",
            confidence_score=0.75,
            reasoning="Sea trials certificate pending",
            evidence_page_number=1,
        )
        session.add_all([tender, clause, bidder, eval_item])
        await session.commit()

        tender_id_str = str(tender.id)
        eval_id_str = str(eval_item.id)

    # 1. Login as AUDITOR
    auditor_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": f"auditor_{suffix}@defense.gov.in", "password": "AuditorPass2026!"},
    )
    assert auditor_login.status_code == 200
    auditor_token = auditor_login.json()["access_token"]
    assert "AUDITOR" in auditor_login.json()["roles"]

    # 2. Login as PROCUREMENT_OFFICER
    officer_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": f"officer_{suffix}@defense.gov.in", "password": "OfficerPass2026!"},
    )
    assert officer_login.status_code == 200
    officer_token = officer_login.json()["access_token"]
    assert "PROCUREMENT_OFFICER" in officer_login.json()["roles"]

    # 3. AUDITOR attempts to override: MUST RECEIVE 403 FORBIDDEN!
    auditor_override = await async_client.post(
        f"/api/v1/tenders/{tender_id_str}/evaluations/{eval_id_str}/override",
        headers={"Authorization": f"Bearer {auditor_token}"},
        json={
            "override_status": "PASS",
            "override_reason": "Auditor unauthorized approval attempt",
        },
    )
    assert auditor_override.status_code == 403, "Auditor MUST receive 403 Forbidden on override attempts!"
    assert "evaluation:override" in auditor_override.json()["detail"]

    # 4. PROCUREMENT_OFFICER applies override: MUST SUCCEED (200 OK)!
    officer_override = await async_client.post(
        f"/api/v1/tenders/{tender_id_str}/evaluations/{eval_id_str}/override",
        headers={"Authorization": f"Bearer {officer_token}"},
        json={
            "override_status": "PASS",
            "override_reason": "Certified sea trial certificate verified in official annexure.",
        },
    )
    assert officer_override.status_code == 200
    assert officer_override.json()["override_status"] == "PASS"
    assert officer_override.json()["override_reason"] == "Certified sea trial certificate verified in official annexure."
