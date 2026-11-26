"""Comprehensive Phase 1.2 tests for Organization Onboarding, Membership Control,
Invitation Lifecycle, and Cross-Tenant Isolation against live PostgreSQL.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal, init_db
from app.core.security import hash_token
from app.main import app
from app.models.auth import OrganizationInvitation
from app.models.user import User
from tests_auth_helper import create_test_officer_and_headers


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_organization_profile_and_role_matrix():
    await init_db()
    uid = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        org_a, _, admin_headers = await create_test_officer_and_headers(db, role_name="ORG_ADMIN")
        _, _, officer_headers = await create_test_officer_and_headers(db, role_name="PROCUREMENT_OFFICER")
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/api/v1/organizations/me", headers=admin_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == org_a.name
        assert data["total_members"] == 1
        assert data["active_members"] == 1

        # Authorized update
        upd = await client.put(
            "/api/v1/organizations/me",
            json={"name": f"Org Alpha Updated {uid}", "domain": "alpha.gov.in"},
            headers=admin_headers,
        )
        assert upd.status_code == 200
        assert upd.json()["name"] == f"Org Alpha Updated {uid}"
        assert upd.json()["domain"] == "alpha.gov.in"

        # Unauthorized update (PROCUREMENT_OFFICER lacks organization:update)
        forbidden = await client.put(
            "/api/v1/organizations/me",
            json={"name": "Hijacked Name"},
            headers=officer_headers,
        )
        assert forbidden.status_code == 403

        # Role matrix
        roles_res = await client.get("/api/v1/organizations/roles", headers=admin_headers)
        assert roles_res.status_code == 200
        role_map = {r["name"]: r for r in roles_res.json()}
        assert role_map["SUPER_ADMIN"]["assignable_by_org_admin"] is False
        assert role_map["PROCUREMENT_OFFICER"]["assignable_by_org_admin"] is True


@pytest.mark.anyio
async def test_invitation_lifecycle_validation_revocation_resend_and_replay():
    await init_db()
    uid = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        org_a, admin_a, admin_headers = await create_test_officer_and_headers(db, role_name="ORG_ADMIN")
        _, _, officer_headers = await create_test_officer_and_headers(db, role_name="PROCUREMENT_OFFICER")
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Unauthorized invitation creation (officer lacks user:invite)
        unauth = await client.post(
            "/api/v1/auth/invitations",
            json={"email": f"new_{uid}@orga.in", "role_name": "AUDITOR"},
            headers=officer_headers,
        )
        assert unauth.status_code == 403

        # 2. Disallowed SUPER_ADMIN invitation
        sa_attempt = await client.post(
            "/api/v1/auth/invitations",
            json={"email": f"sa_{uid}@orga.in", "role_name": "SUPER_ADMIN"},
            headers=admin_headers,
        )
        assert sa_attempt.status_code == 403

        # 3. Existing registered user invitation blocked (409)
        existing_attempt = await client.post(
            "/api/v1/auth/invitations",
            json={"email": admin_a.email, "role_name": "AUDITOR"},
            headers=admin_headers,
        )
        assert existing_attempt.status_code == 409

        # 4. Valid invitation creation
        invitee_email = f"member_{uid}@orga.in"
        inv_res = await client.post(
            "/api/v1/auth/invitations",
            json={"email": invitee_email, "role_name": "PROCUREMENT_OFFICER"},
            headers=admin_headers,
        )
        assert inv_res.status_code == 201
        inv_data = inv_res.json()
        token_1 = inv_data["invitation_token"]
        inv_id_1 = inv_data["id"]

        # 5. Duplicate pending invitation blocked (409)
        dup_res = await client.post(
            "/api/v1/auth/invitations",
            json={"email": invitee_email, "role_name": "AUDITOR"},
            headers=admin_headers,
        )
        assert dup_res.status_code == 409

        # 6. Validate pending token
        val_res = await client.get(f"/api/v1/auth/invitations/validate?token={token_1}")
        assert val_res.status_code == 200
        assert val_res.json()["valid"] is True
        assert val_res.json()["status"] == "PENDING"
        assert val_res.json()["role_name"] == "PROCUREMENT_OFFICER"

        # 7. Resend revokes token_1 and issues token_2
        resend_res = await client.post(
            f"/api/v1/organizations/me/invitations/{inv_id_1}/resend",
            headers=admin_headers,
        )
        assert resend_res.status_code == 201
        token_2 = resend_res.json()["invitation_token"]
        inv_id_2 = resend_res.json()["id"]
        assert token_2 != token_1

        val_old = await client.get(f"/api/v1/auth/invitations/validate?token={token_1}")
        assert val_old.json()["valid"] is False
        assert val_old.json()["status"] == "REVOKED"

        # 8. Email mismatch on accept fails (400)
        mismatch = await client.post(
            "/api/v1/auth/invitations/accept",
            json={
                "invitation_token": token_2,
                "email": f"wrong_{uid}@orga.in",
                "password": "StrongPass123!",
                "full_name": "Wrong Person",
            },
        )
        assert mismatch.status_code == 400

        # 9. Valid single-use acceptance succeeds (201) and scopes user to org_a
        accept_res = await client.post(
            "/api/v1/auth/invitations/accept",
            json={
                "invitation_token": token_2,
                "email": invitee_email,
                "password": "StrongPass123!",
                "full_name": "Invited Officer",
            },
        )
        assert accept_res.status_code == 201
        accept_body = accept_res.json()
        assert accept_body["organization_id"] == str(org_a.id)
        assert accept_body["roles"] == ["PROCUREMENT_OFFICER"]

        # 10. Repeated acceptance / token replay fails (400)
        replay = await client.post(
            "/api/v1/auth/invitations/accept",
            json={
                "invitation_token": token_2,
                "email": invitee_email,
                "password": "StrongPass123!",
                "full_name": "Replay Attempt",
            },
        )
        assert replay.status_code == 400

        # 11. Explicit revocation & expired token checks
        rev_email = f"revoked_{uid}@orga.in"
        rev_create = await client.post(
            "/api/v1/auth/invitations",
            json={"email": rev_email, "role_name": "AUDITOR"},
            headers=admin_headers,
        )
        assert rev_create.status_code == 201
        rev_token = rev_create.json()["invitation_token"]
        rev_id = rev_create.json()["id"]

        rev_action = await client.post(
            f"/api/v1/organizations/me/invitations/{rev_id}/revoke",
            headers=admin_headers,
        )
        assert rev_action.status_code == 200
        assert rev_action.json()["status"] == "REVOKED"

        rev_accept = await client.post(
            "/api/v1/auth/invitations/accept",
            json={
                "invitation_token": rev_token,
                "email": rev_email,
                "password": "StrongPass123!",
                "full_name": "Revoked User",
            },
        )
        assert rev_accept.status_code == 400

        # 12. Expired token check
        exp_email = f"expired_{uid}@orga.in"
        exp_create = await client.post(
            "/api/v1/auth/invitations",
            json={"email": exp_email, "role_name": "BIDDER"},
            headers=admin_headers,
        )
        exp_token = exp_create.json()["invitation_token"]
        exp_id = uuid.UUID(exp_create.json()["id"])

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(OrganizationInvitation)
                .where(OrganizationInvitation.id == exp_id)
                .values(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
            )
            await db.commit()

        exp_val = await client.get(f"/api/v1/auth/invitations/validate?token={exp_token}")
        assert exp_val.json()["valid"] is False
        assert exp_val.json()["status"] == "EXPIRED"

        exp_accept = await client.post(
            "/api/v1/auth/invitations/accept",
            json={
                "invitation_token": exp_token,
                "email": exp_email,
                "password": "StrongPass123!",
                "full_name": "Expired User",
            },
        )
        assert exp_accept.status_code == 400


@pytest.mark.anyio
async def test_member_management_safeguards_and_cross_tenant_isolation():
    await init_db()
    uid = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        org_a, admin_a, headers_a = await create_test_officer_and_headers(db, role_name="ORG_ADMIN")
        org_b, admin_b, headers_b = await create_test_officer_and_headers(db, role_name="ORG_ADMIN")
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Invite and accept a second user in Org A
        member_email = f"staff_a_{uid}@orga.in"
        inv = await client.post(
            "/api/v1/auth/invitations",
            json={"email": member_email, "role_name": "AUDITOR"},
            headers=headers_a,
        )
        inv_b = await client.post(
            "/api/v1/auth/invitations",
            json={"email": f"staff_b_{uid}@orgb.in", "role_name": "AUDITOR"},
            headers=headers_b,
        )
        inv_b_id = inv_b.json()["id"]

        acc = await client.post(
            "/api/v1/auth/invitations/accept",
            json={
                "invitation_token": inv.json()["invitation_token"],
                "email": member_email,
                "password": "StrongPass123!",
                "full_name": "Staff Alpha",
            },
        )
        member_a_id = acc.json()["user_id"]

        # Last-admin protection: admin_a cannot demote or deactivate themselves
        self_demote = await client.put(
            f"/api/v1/organizations/me/members/{admin_a.id}/role",
            json={"role_name": "AUDITOR"},
            headers=headers_a,
        )
        assert self_demote.status_code == 403

        self_deact = await client.put(
            f"/api/v1/organizations/me/members/{admin_a.id}/status",
            json={"is_active": False},
            headers=headers_a,
        )
        assert self_deact.status_code == 403

        # Cannot assign SUPER_ADMIN to member_a
        sa_role = await client.put(
            f"/api/v1/organizations/me/members/{member_a_id}/role",
            json={"role_name": "SUPER_ADMIN"},
            headers=headers_a,
        )
        assert sa_role.status_code == 403

        # Valid role change & member listing filter
        role_upd = await client.put(
            f"/api/v1/organizations/me/members/{member_a_id}/role",
            json={"role_name": "PROCUREMENT_OFFICER"},
            headers=headers_a,
        )
        assert role_upd.status_code == 200
        assert role_upd.json()["roles"] == ["PROCUREMENT_OFFICER"]

        # Cross-tenant isolation: Org A cannot see or mutate Org B's members or invitations
        members_a = await client.get("/api/v1/organizations/me/members", headers=headers_a)
        assert members_a.status_code == 200
        member_emails_a = {m["email"] for m in members_a.json()["items"]}
        assert admin_b.email not in member_emails_a

        cross_role = await client.put(
            f"/api/v1/organizations/me/members/{admin_b.id}/role",
            json={"role_name": "BIDDER"},
            headers=headers_a,
        )
        assert cross_role.status_code == 404

        cross_del = await client.delete(
            f"/api/v1/organizations/me/members/{admin_b.id}",
            headers=headers_a,
        )
        assert cross_del.status_code == 404

        cross_rev = await client.post(
            f"/api/v1/organizations/me/invitations/{inv_b_id}/revoke",
            headers=headers_a,
        )
        assert cross_rev.status_code == 404

        # Deactivate & remove member_a
        deact = await client.put(
            f"/api/v1/organizations/me/members/{member_a_id}/status",
            json={"is_active": False},
            headers=headers_a,
        )
        assert deact.status_code == 200
        assert deact.json()["is_active"] is False

        rem = await client.delete(
            f"/api/v1/organizations/me/members/{member_a_id}",
            headers=headers_a,
        )
        assert rem.status_code == 200
