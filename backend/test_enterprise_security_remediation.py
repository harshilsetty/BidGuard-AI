import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import select, text, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import event

from app.main import app
from app.core.config import settings
from app.core.database import Base, get_db, _enable_sqlite_foreign_keys
from app.core.security import create_access_token, hash_password
from app.models.audit import AuditLog
from app.models.bidder import Bidder
from app.models.clause import TenderClause
from app.models.evaluation import ComplianceEvaluation
from app.models.organization import Organization
from app.models.rbac import Role, UserRole
from app.models.tender import Tender
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.embedding_service import EmbeddingService, NvidiaEmbeddingProvider
from app.services.rbac_service import RBACService
from app.api.v1.auth import reset_auth_rate_limiter

TEST_DB_PATH = "./test_security_remediation.db"
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

test_engine = create_async_engine(TEST_DB_URL, echo=False, future=True)
event.listen(test_engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
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
async def setup_test_db():
    reset_auth_rate_limiter()
    app.dependency_overrides[get_db] = override_get_db
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


async def _create_org_and_user(
    session: AsyncSession,
    org_name: str,
    email: str,
    role_name: str,
    is_active: bool = True,
    org_active: bool = True,
):
    org = Organization(
        id=uuid.uuid4(),
        name=org_name,
        slug=f"{org_name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
        is_active=org_active,
    )
    session.add(org)
    await session.flush()

    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("StrongPass123!"),
        full_name=f"{role_name} User",
        organization_id=org.id,
        is_active=is_active,
        is_verified=True,
    )
    session.add(user)
    await session.flush()

    role = (await session.execute(select(Role).where(Role.name == role_name))).scalar_one()
    session.add(UserRole(user_id=user.id, role_id=role.id, organization_id=org.id))
    await session.flush()

    roles, perms = await RBACService.get_user_roles_and_permissions(user.id, session)
    token = create_access_token(str(user.id), str(org.id), roles, perms)
    return org, user, token


# ---------------------------------------------------------------------------
# 1. Authentication & Edge-Case Hardening
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_unauthenticated_and_malformed_tokens_blocked(client: httpx.AsyncClient):
    """F-01 & F-06: All business endpoints reject missing/malformed/expired tokens with 401 (never 500)."""
    tid = str(uuid.uuid4())
    bid = str(uuid.uuid4())
    eid = str(uuid.uuid4())

    protected_gets = [
        "/api/v1/tenders",
        f"/api/v1/tenders/{tid}",
        f"/api/v1/tenders/{tid}/clauses",
        f"/api/v1/tenders/{tid}/bidders",
        f"/api/v1/tenders/{tid}/bidders/{bid}",
        f"/api/v1/tenders/{tid}/bidders/{bid}/evidence-fusion",
        f"/api/v1/tenders/{tid}/bidders/{bid}/cross-source-verification",
        f"/api/v1/tenders/{tid}/evaluations/matrix",
        f"/api/v1/tenders/{tid}/evaluations/{eid}",
        f"/api/v1/tenders/{tid}/bidders/{bid}/score",
        f"/api/v1/tenders/{tid}/ranking",
        f"/api/v1/tenders/{tid}/bidders/{bid}/verification-summary",
        f"/api/v1/tenders/{tid}/bidders/{bid}/verification-history",
        f"/api/v1/tenders/{tid}/review-queue",
        "/api/v1/statutory/status",
        "/api/v1/statutory/adapters",
        "/api/v1/mock-sources",
        "/api/v1/audit/logs",
    ]
    for url in protected_gets:
        r_anon = await client.get(url)
        assert r_anon.status_code == 401, f"Expected 401 for unauthenticated GET {url}, got {r_anon.status_code}"

        r_bad = await client.get(url, headers={"Authorization": "Bearer not.a.jwt"})
        assert r_bad.status_code == 401, f"Expected 401 for malformed JWT on {url}, got {r_bad.status_code}"

    # Unauthenticated override must return 401
    r_ovr = await client.post(
        f"/api/v1/evaluations/{eid}/override",
        json={"override_status": "PASS", "override_reason": "Unauthorized attempt"},
    )
    assert r_ovr.status_code == 401


@pytest.mark.anyio
async def test_public_registration_blocked_and_invitation_flow(client: httpx.AsyncClient):
    """F-09: Public /register is disabled (403); invitation flow is single-use and blocks SUPER_ADMIN."""
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "attacker@evil.com",
            "password": "StrongPassword123!",
            "full_name": "Evil Admin",
            "organization_name": "Evil Corp",
        },
    )
    assert reg_resp.status_code == 403

    async with TestSessionLocal() as session:
        org, admin_user, admin_token = await _create_org_and_user(
            session, "Gov Ministry", "admin@ministry.gov.in", "ORG_ADMIN"
        )
        await session.commit()

    # Cannot invite SUPER_ADMIN
    super_inv = await client.post(
        "/api/v1/auth/invitations",
        json={"email": "x@ministry.gov.in", "role_name": "SUPER_ADMIN"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert super_inv.status_code == 403

    # Valid invitation for PROCUREMENT_OFFICER
    inv_resp = await client.post(
        "/api/v1/auth/invitations",
        json={"email": "officer@ministry.gov.in", "role_name": "PROCUREMENT_OFFICER"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert inv_resp.status_code == 201
    inv_token = inv_resp.json()["invitation_token"]

    # Accept invitation
    acc_resp = await client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "invitation_token": inv_token,
            "email": "officer@ministry.gov.in",
            "password": "OfficerPass123!",
            "full_name": "Officer One",
        },
    )
    assert acc_resp.status_code == 201
    assert "PROCUREMENT_OFFICER" in acc_resp.json()["roles"]

    # Replay invitation (single-use check) -> 400
    replay_resp = await client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "invitation_token": inv_token,
            "email": "officer@ministry.gov.in",
            "password": "OfficerPass123!",
            "full_name": "Officer One",
        },
    )
    assert replay_resp.status_code == 400


@pytest.mark.anyio
async def test_concurrent_refresh_token_race_condition(client: httpx.AsyncClient):
    """F-05: Concurrent refresh requests with the same token cannot both succeed."""
    async with TestSessionLocal() as session:
        await _create_org_and_user(session, "Concurrency Org", "race@org.gov.in", "PROCUREMENT_OFFICER")
        await session.commit()

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "race@org.gov.in", "password": "StrongPass123!"},
    )
    assert login_resp.status_code == 200
    raw_refresh = login_resp.cookies.get("bidguard_refresh_token")
    assert raw_refresh

    r1, r2 = await asyncio.gather(
        client.post("/api/v1/auth/refresh", json={"refresh_token": raw_refresh}),
        client.post("/api/v1/auth/refresh", json={"refresh_token": raw_refresh}),
    )
    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [200, 401], f"Expected exactly one 200 and one 401 on concurrent refresh, got {statuses}"


@pytest.mark.anyio
async def test_live_permission_revocation_immediate_denial(client: httpx.AsyncClient):
    """F-06: Revoking evaluation:override in DB denies request immediately even with existing JWT."""
    async with TestSessionLocal() as session:
        org, officer, officer_token = await _create_org_and_user(
            session, "Live RBAC Org", "live@org.gov.in", "PROCUREMENT_OFFICER"
        )
        tender = Tender(
            id=uuid.uuid4(),
            organization_id=org.id,
            title="Live RBAC Tender",
            total_pages=1,
            extraction_status="READY",
            next_clause_seq={"TECH": 2},
        )
        clause = TenderClause(
            id=uuid.uuid4(),
            tender_id=tender.id,
            clause_code="TECH-01",
            category="TECHNICAL",
            title="Spec",
            description="Desc",
            source_text="Src",
            is_mandatory=True,
            page_number=1,
        )
        bidder = Bidder(id=uuid.uuid4(), tender_id=tender.id, company_name="Test Co", final_status="UNDER_REVIEW")
        ev = ComplianceEvaluation(
            id=uuid.uuid4(),
            bidder_id=bidder.id,
            clause_id=clause.id,
            status="REVIEW",
            confidence_score=0.5,
            reasoning="Pending",
        )
        session.add_all([tender, clause, bidder, ev])
        await session.commit()
        ev_id = str(ev.id)
        officer_id = officer.id

    # 1. Works before revocation
    ok_resp = await client.post(
        f"/api/v1/evaluations/{ev_id}/override",
        json={"override_status": "PASS", "override_reason": "Verified docs"},
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert ok_resp.status_code == 200

    # 2. Revoke PROCUREMENT_OFFICER and assign AUDITOR in DB (without changing officer_token!)
    async with TestSessionLocal() as session:
        await session.execute(delete(UserRole).where(UserRole.user_id == officer_id))
        auditor_role = (await session.execute(select(Role).where(Role.name == "AUDITOR"))).scalar_one()
        session.add(UserRole(user_id=officer_id, role_id=auditor_role.id))
        await session.commit()

    # 3. Same JWT must now be denied immediately with 403
    denied_resp = await client.post(
        f"/api/v1/evaluations/{ev_id}/override",
        json={"override_status": "FAIL", "override_reason": "Should be denied"},
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert denied_resp.status_code == 403


# ---------------------------------------------------------------------------
# 2. Cross-Tenant Isolation & Legacy NULL Tender Blocking
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_cross_tenant_and_legacy_null_isolation(client: httpx.AsyncClient):
    """F-01: Cross-tenant access and unassigned NULL-org legacy tenders return 404 to tenant users."""
    async with TestSessionLocal() as session:
        org_a, _, token_a = await _create_org_and_user(session, "Org Alpha", "a@alpha.gov.in", "PROCUREMENT_OFFICER")
        org_b, _, token_b = await _create_org_and_user(session, "Org Beta", "b@beta.gov.in", "PROCUREMENT_OFFICER")
        _, _, bidder_token_a = await _create_org_and_user(session, "Org Alpha Bidder", "bid@alpha.gov.in", "BIDDER")

        tender_a = Tender(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            title="Alpha Secret Tender",
            total_pages=1,
            extraction_status="READY",
            next_clause_seq={"TECH": 1},
        )
        legacy_tender = Tender(
            id=uuid.uuid4(),
            organization_id=None,
            title="Unassigned Legacy Tender",
            total_pages=1,
            extraction_status="READY",
            next_clause_seq={"TECH": 1},
        )
        session.add_all([tender_a, legacy_tender])
        await session.commit()
        ta_id = str(tender_a.id)
        leg_id = str(legacy_tender.id)

    # Org B cannot see Org A's tender or legacy tender
    for target_id in (ta_id, leg_id):
        assert (await client.get(f"/api/v1/tenders/{target_id}", headers={"Authorization": f"Bearer {token_b}"})).status_code == 404
        assert (await client.get(f"/api/v1/tenders/{target_id}/bidders", headers={"Authorization": f"Bearer {token_b}"})).status_code == 404
        assert (await client.get(f"/api/v1/tenders/{target_id}/ranking", headers={"Authorization": f"Bearer {token_b}"})).status_code == 404
        assert (await client.get(f"/api/v1/tenders/{target_id}/review-queue", headers={"Authorization": f"Bearer {token_b}"})).status_code == 404

    # Org A listing does not leak legacy NULL tender
    list_a = (await client.get("/api/v1/tenders", headers={"Authorization": f"Bearer {token_a}"})).json()
    ids_a = [item["id"] for item in list_a]
    assert ta_id in ids_a
    assert leg_id not in ids_a

    # BIDDER role cannot delete bidder or add clauses (403)
    del_resp = await client.delete(
        f"/api/v1/tenders/{ta_id}/bidders/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {bidder_token_a}"},
    )
    assert del_resp.status_code == 403


# ---------------------------------------------------------------------------
# 3. SQLite Foreign-Key Enforcement (F-03)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_sqlite_foreign_key_constraint_enforced():
    """Verify PRAGMA foreign_keys=ON rejects invalid organization_id on tenders."""
    async with TestSessionLocal() as session:
        fk_state = (await session.execute(text("PRAGMA foreign_keys"))).scalar()
        assert fk_state == 1

        bad_tender = Tender(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),  # Non-existent org
            title="Orphan Tender",
            total_pages=1,
            extraction_status="UPLOADED",
            next_clause_seq={},
        )
        session.add(bad_tender)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


# ---------------------------------------------------------------------------
# 4. Embedding Service Production Policy & NVIDIA Contract (F-04, F-08)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_embedding_service_production_stub_ban_and_nvidia_contract(monkeypatch):
    """F-04 & F-08: Production forbids StubEmbeddingProvider even if AUTH_DEV_MODE=True; NVIDIA uses input_type."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "AUTH_DEV_MODE", True)
    monkeypatch.setattr(settings, "ALLOW_MOCK_EMBEDDINGS", True)
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", "")

    with pytest.raises(RuntimeError, match="StubEmbeddingProvider is forbidden"):
        EmbeddingService()

    # Verify NvidiaEmbeddingProvider sends input_type="passage" and "query"
    from unittest.mock import patch
    with patch("app.services.embedding_service.AsyncOpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        provider = NvidiaEmbeddingProvider(api_key="nvapi-test-key", model_name="nvidia/nemotron-3.5-embed-1b", expected_dim=2048)
        mock_item = MagicMock()
        mock_item.embedding = [0.1] * 2048
        mock_resp = MagicMock()
        mock_resp.data = [mock_item]
        provider._client.embeddings.create = AsyncMock(return_value=mock_resp)

    await provider.embed_texts(["sample passage"])
    _, kwargs_passage = provider._client.embeddings.create.call_args
    assert kwargs_passage["extra_body"] == {"input_type": "passage"}

    await provider.embed_query("sample query")
    _, kwargs_query = provider._client.embeddings.create.call_args
    assert kwargs_query["extra_body"] == {"input_type": "query"}

    svc = EmbeddingService(provider=provider)
    assert svc.validate_embedding_space("nvidia/nemotron-3.5-embed-1b") is True
    assert svc.validate_embedding_space("stub-deterministic-2048") is False
    assert svc.validate_embedding_space(None) is False

    # Verify retrieval refuses incompatible embedding spaces
    from app.services.evidence_retrieval import retrieve_evidence_for_clause
    from app.schemas.bidder import DocumentChunkItem
    bid_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    incompatible_chunk = DocumentChunkItem(
        chunk_id="c1",
        bidder_id=bid_id,
        document_id=doc_id,
        filename="b.pdf",
        page_number=1,
        chunk_index=0,
        chunk_text="Turnover is 10 Cr",
        embedding=[0.1] * 2048,
        embedding_model="stub-deterministic-2048",
    )
    with pytest.raises(ValueError, match="Embedding-space mismatch"):
        await retrieve_evidence_for_clause(
            clause={"clause_code": "FIN-01", "title": "Turnover"},
            bidder_id=bid_id,
            chunks=[incompatible_chunk],
            embedding_service=svc,
        )
