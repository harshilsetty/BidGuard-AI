"""Phase 1.4 End-to-End Role Journeys (Journeys A-E) & Cross-Tenant Isolation Suite.

Exercises real FastAPI endpoints against live PostgreSQL 16 + pgvector without
mutating the Golden Demo database.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import AsyncSessionLocal, init_db
from app.main import app
from tests_auth_helper import create_test_officer_and_headers


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _login_user(client: AsyncClient, email: str, password: str = "TestSuitePass123!"):
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"], dict(res.cookies)


@pytest.mark.anyio
async def test_journey_a_org_admin_and_cross_tenant_audit_isolation():
    await init_db()
    async with AsyncSessionLocal() as db:
        org_a, admin_a, _ = await create_test_officer_and_headers(db, role_name="ORG_ADMIN")
        org_b, admin_b, _ = await create_test_officer_and_headers(db, role_name="ORG_ADMIN")
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Authenticate Org A Admin + Org B Admin
        token_a, cookies_a = await _login_user(client, admin_a.email)
        token_b, _ = await _login_user(client, admin_b.email)

        # 2. Restore session via HttpOnly refresh cookie
        refresh_res = await client.post("/api/v1/auth/refresh", cookies=cookies_a)
        assert refresh_res.status_code == 200
        token_a = refresh_res.json()["access_token"]
        cookies_a = dict(refresh_res.cookies)
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 3-4. Enter org workspace & view details
        org_res = await client.get("/api/v1/organizations/me", headers=headers_a)
        assert org_res.status_code == 200
        assert org_res.json()["id"] == str(org_a.id)

        # 5. View team members
        members_res = await client.get("/api/v1/organizations/me/members", headers=headers_a)
        assert members_res.status_code == 200
        assert members_res.json()["total"] == 1

        # 6-8. Create invitation, inspect list, revoke invitation
        inv_email = f"journey_a_{uuid.uuid4().hex[:6]}@orga.in"
        inv_create = await client.post(
            "/api/v1/auth/invitations",
            json={"email": inv_email, "role_name": "PROCUREMENT_OFFICER"},
            headers=headers_a,
        )
        assert inv_create.status_code == 201
        inv_id = inv_create.json()["id"]

        inv_list = await client.get("/api/v1/organizations/me/invitations?status=PENDING", headers=headers_a)
        assert inv_list.status_code == 200
        assert any(i["id"] == inv_id for i in inv_list.json()["items"])

        inv_revoke = await client.post(
            f"/api/v1/organizations/me/invitations/{inv_id}/revoke",
            headers=headers_a,
        )
        assert inv_revoke.status_code == 200
        assert inv_revoke.json()["status"] == "REVOKED"

        # 9. Inspect audit activity & verify Org B cannot see Org A's audit logs
        audit_a = await client.get("/api/v1/audit/logs", headers=headers_a)
        assert audit_a.status_code == 200
        assert all(item["organization_id"] == str(org_a.id) for item in audit_a.json()["items"])

        audit_b = await client.get("/api/v1/audit/logs", headers=headers_b)
        assert audit_b.status_code == 200
        assert all(item["organization_id"] == str(org_b.id) for item in audit_b.json()["items"])

        # 10. Sign out & verify refresh cookie revoked
        logout_res = await client.post("/api/v1/auth/logout", cookies=cookies_a)
        assert logout_res.status_code == 200
        post_logout = await client.post("/api/v1/auth/refresh", cookies=cookies_a)
        assert post_logout.status_code == 401


@pytest.mark.anyio
async def test_journeys_b_c_d_e_role_boundaries():
    await init_db()
    async with AsyncSessionLocal() as db:
        _, officer, _ = await create_test_officer_and_headers(db, role_name="PROCUREMENT_OFFICER")
        _, auditor, _ = await create_test_officer_and_headers(db, role_name="AUDITOR")
        _, bidder, _ = await create_test_officer_and_headers(db, role_name="BIDDER")
        _, super_admin, _ = await create_test_officer_and_headers(db, role_name="SUPER_ADMIN")
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Journey B — PROCUREMENT_OFFICER
        off_tok, off_cookies = await _login_user(client, officer.email)
        off_h = {"Authorization": f"Bearer {off_tok}"}
        assert (await client.get("/api/v1/tenders", headers=off_h)).status_code == 200
        assert (await client.get("/api/v1/organizations/me", headers=off_h)).status_code == 200
        # Restricted admin action denied
        assert (
            await client.post(
                "/api/v1/auth/invitations",
                json={"email": "blocked@org.in", "role_name": "BIDDER"},
                headers=off_h,
            )
        ).status_code == 403
        assert (await client.post("/api/v1/auth/logout", cookies=off_cookies)).status_code == 200

        # Journey C — AUDITOR (read-only)
        aud_tok, aud_cookies = await _login_user(client, auditor.email)
        aud_h = {"Authorization": f"Bearer {aud_tok}"}
        assert (await client.get("/api/v1/tenders", headers=aud_h)).status_code == 200
        assert (await client.get("/api/v1/audit/logs", headers=aud_h)).status_code == 200
        # Unauthorized mutation denied
        assert (
            await client.put("/api/v1/organizations/me", json={"name": "Nope"}, headers=aud_h)
        ).status_code == 403
        assert (await client.post("/api/v1/auth/logout", cookies=aud_cookies)).status_code == 200

        # Journey D — BIDDER (restricted read-only)
        bid_tok, bid_cookies = await _login_user(client, bidder.email)
        bid_h = {"Authorization": f"Bearer {bid_tok}"}
        assert (await client.get("/api/v1/auth/me", headers=bid_h)).status_code == 200
        assert (await client.get("/api/v1/tenders", headers=bid_h)).status_code == 200
        # Denied org & audit endpoints
        assert (await client.get("/api/v1/organizations/me", headers=bid_h)).status_code == 403
        assert (await client.get("/api/v1/audit/logs", headers=bid_h)).status_code == 403
        assert (await client.post("/api/v1/auth/logout", cookies=bid_cookies)).status_code == 200

        # Journey E — SUPER_ADMIN (platform oversight & auditable)
        sa_tok, sa_cookies = await _login_user(client, super_admin.email)
        sa_h = {"Authorization": f"Bearer {sa_tok}"}
        assert (await client.get("/api/v1/organizations/me", headers=sa_h)).status_code == 200
        sa_audit = await client.get("/api/v1/audit/logs", headers=sa_h)
        assert sa_audit.status_code == 200
        assert sa_audit.json()["total"] >= 1
        assert (await client.post("/api/v1/auth/logout", cookies=sa_cookies)).status_code == 200
