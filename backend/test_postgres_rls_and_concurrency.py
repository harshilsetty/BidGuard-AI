"""Live PostgreSQL 16 + pgvector RLS, Connection-Pool, Audit Trigger & Concurrency Suite.

Executes against real PostgreSQL 16 (`bidguard_fresh_test`) using the restricted
non-superuser, NOBYPASSRLS runtime role `bidguard_app`.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text, select
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import hash_password, hash_token
from app.models.auth import RefreshToken
from app.services.auth_service import AuthService
from app.services.rbac_service import RBACService

ADMIN_PG_URL = "postgresql+asyncpg://postgres:postgrespassword@127.0.0.1:5432/bidguard_fresh_test"
APP_PG_URL = "postgresql+asyncpg://bidguard_app:bidguard_app_test_pw@127.0.0.1:5432/bidguard_fresh_test"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_postgres_role_is_restricted_and_rls_enforced():
    """Workstreams B & E: Verify bidguard_app has no SUPERUSER/BYPASSRLS and RLS blocks all cross-tenant access."""
    admin_eng = create_async_engine(ADMIN_PG_URL, echo=False)
    app_eng = create_async_engine(APP_PG_URL, echo=False, pool_size=1, max_overflow=0)
    AdminSL = async_sessionmaker(admin_eng, class_=AsyncSession, expire_on_commit=False)
    AppSL = async_sessionmaker(app_eng, class_=AsyncSession, expire_on_commit=False)

    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    tender_a = uuid.uuid4()
    tender_b = uuid.uuid4()
    clause_a = uuid.uuid4()
    clause_b = uuid.uuid4()
    bidder_a = uuid.uuid4()
    bidder_b = uuid.uuid4()
    doc_a = uuid.uuid4()
    doc_b = uuid.uuid4()
    chunk_a = uuid.uuid4()
    chunk_b = uuid.uuid4()
    eval_a = uuid.uuid4()
    eval_b = uuid.uuid4()
    stat_a = uuid.uuid4()
    stat_b = uuid.uuid4()
    rec_a = uuid.uuid4()
    rec_b = uuid.uuid4()
    audit_a = uuid.uuid4()
    audit_b = uuid.uuid4()
    inv_a = uuid.uuid4()
    inv_b = uuid.uuid4()
    rt_a = uuid.uuid4()
    rt_b = uuid.uuid4()
    ur_a = uuid.uuid4()
    ur_b = uuid.uuid4()

    try:
        # 1. Seed Org A & Org B hierarchies using admin role
        async with AdminSL() as s:
            await RBACService.ensure_system_roles_and_permissions(s)
            role_id = (await s.execute(text("SELECT id FROM roles WHERE name = 'PROCUREMENT_OFFICER'"))).scalar_one()

            await s.execute(
                text(
                    "INSERT INTO organizations (id, name, slug, is_active, created_at, updated_at) "
                    "VALUES (:id, :name, :slug, true, NOW(), NOW())"
                ),
                [
                    {"id": org_a, "name": "PG Org A", "slug": f"pg-a-{org_a.hex[:6]}"},
                    {"id": org_b, "name": "PG Org B", "slug": f"pg-b-{org_b.hex[:6]}"},
                ],
            )
            pw = hash_password("PgStrongPass123!")
            await s.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, full_name, organization_id, is_active, is_verified, created_at, updated_at) "
                    "VALUES (:id, :email, :pw, :fn, :org, true, true, NOW(), NOW())"
                ),
                [
                    {"id": user_a, "email": f"ua-{org_a.hex[:6]}@a.gov", "pw": pw, "fn": "User A", "org": org_a},
                    {"id": user_b, "email": f"ub-{org_b.hex[:6]}@b.gov", "pw": pw, "fn": "User B", "org": org_b},
                ],
            )
            await s.execute(
                text(
                    "INSERT INTO user_roles (id, user_id, role_id, organization_id, created_at, updated_at) "
                    "VALUES (:id, :u, :r, :org, NOW(), NOW())"
                ),
                [
                    {"id": ur_a, "u": user_a, "r": role_id, "org": org_a},
                    {"id": ur_b, "u": user_b, "r": role_id, "org": org_b},
                ],
            )
            await s.execute(
                text(
                    "INSERT INTO refresh_tokens (id, user_id, token_hash, token_family_id, expires_at, created_at, updated_at) "
                    "VALUES (:id, :u, :th, :fam, NOW() + interval '7 days', NOW(), NOW())"
                ),
                [
                    {"id": rt_a, "u": user_a, "th": hash_token(f"rta-{org_a}"), "fam": uuid.uuid4()},
                    {"id": rt_b, "u": user_b, "th": hash_token(f"rtb-{org_b}"), "fam": uuid.uuid4()},
                ],
            )
            await s.execute(
                text(
                    "INSERT INTO tenders (id, organization_id, title, total_pages, extraction_status, next_clause_seq, created_at, updated_at) "
                    "VALUES (:id, :org, :title, 1, 'READY', '{}', NOW(), NOW())"
                ),
                [
                    {"id": tender_a, "org": org_a, "title": "Tender A"},
                    {"id": tender_b, "org": org_b, "title": "Tender B"},
                ],
            )
            await s.execute(
                text(
                    "INSERT INTO tender_clauses (id, tender_id, clause_code, category, title, description, source_text, is_mandatory, page_number, created_at, updated_at) "
                    "VALUES (:id, :t, 'TECH-01', 'TECHNICAL', 'T', 'D', 'S', true, 1, NOW(), NOW())"
                ),
                [{"id": clause_a, "t": tender_a}, {"id": clause_b, "t": tender_b}],
            )
            await s.execute(
                text(
                    "INSERT INTO bidders (id, tender_id, company_name, final_status, created_at, updated_at) "
                    "VALUES (:id, :t, :cn, 'UNDER_REVIEW', NOW(), NOW())"
                ),
                [
                    {"id": bidder_a, "t": tender_a, "cn": "Bidder A"},
                    {"id": bidder_b, "t": tender_b, "cn": "Bidder B"},
                ],
            )
            await s.execute(
                text(
                    "INSERT INTO bid_documents (id, bidder_id, file_name, file_path, total_pages, empty_pages_count, extraction_status, created_at, updated_at) "
                    "VALUES (:id, :b, 'f.pdf', '/tmp/f.pdf', 1, 0, 'EXTRACTED', NOW(), NOW())"
                ),
                [{"id": doc_a, "b": bidder_a}, {"id": doc_b, "b": bidder_b}],
            )
            await s.execute(
                text(
                    "INSERT INTO document_chunks (id, bid_document_id, bidder_id, page_number, chunk_index, content, extraction_method, created_at, updated_at) "
                    "VALUES (:id, :d, :b, 1, 0, 'chunk text', 'DIGITAL_TEXT', NOW(), NOW())"
                ),
                [
                    {"id": chunk_a, "d": doc_a, "b": bidder_a},
                    {"id": chunk_b, "d": doc_b, "b": bidder_b},
                ],
            )
            await s.execute(
                text(
                    "INSERT INTO compliance_evaluations (id, bidder_id, clause_id, status, contradiction_detected, risk_level, created_at, updated_at) "
                    "VALUES (:id, :b, :c, 'PASS', false, 'LOW', NOW(), NOW())"
                ),
                [
                    {"id": eval_a, "b": bidder_a, "c": clause_a},
                    {"id": eval_b, "b": bidder_b, "c": clause_b},
                ],
            )
            await s.execute(
                text(
                    "INSERT INTO statutory_verification_records (id, tender_id, bidder_id, verification_id, authority, source_name, query_identifier, identifier_type, mode, connection_status, verification_status, retrieved_at, data_payload, confidence_score, created_at, updated_at) "
                    "VALUES (:id, :t, :b, :vid, 'GSTN', 'Mock GSTN', '27ABC', 'gstin', 'MOCK', 'SUCCESS', 'VERIFIED', NOW(), '{}', 1.0, NOW(), NOW())"
                ),
                [
                    {"id": stat_a, "t": tender_a, "b": bidder_a, "vid": uuid.uuid4()},
                    {"id": stat_b, "t": tender_b, "b": bidder_b, "vid": uuid.uuid4()},
                ],
            )
            await s.execute(
                text(
                    "INSERT INTO recommendation_audit_records (id, tender_id, bidder_id, recommendation_id, event_type, recommendation_type, recommendation_source, score_at_recommendation, risk_at_recommendation, recommendation_summary, model_identifier, action_timestamp, disclaimer, created_at, updated_at) "
                    "VALUES (:id, :t, :b, :rid, 'RECOMMENDATION_GENERATED', 'REVIEW', 'DETERMINISTIC', 90.0, 'LOW', 'Summary', 'model', NOW(), 'Disclaimer', NOW(), NOW())"
                ),
                [
                    {"id": rec_a, "t": tender_a, "b": bidder_a, "rid": uuid.uuid4()},
                    {"id": rec_b, "t": tender_b, "b": bidder_b, "rid": uuid.uuid4()},
                ],
            )
            await s.execute(
                text(
                    "INSERT INTO audit_logs (id, timestamp, organization_id, user_id, action, target_type, target_id, created_at, updated_at) "
                    "VALUES (:id, NOW(), :org, :u, 'TEST_EVENT', 'Tender', :t, NOW(), NOW())"
                ),
                [
                    {"id": audit_a, "org": org_a, "u": user_a, "t": str(tender_a)},
                    {"id": audit_b, "org": org_b, "u": user_b, "t": str(tender_b)},
                ],
            )
            await s.execute(
                text(
                    "INSERT INTO organization_invitations (id, organization_id, email, role_name, token_hash, expires_at, created_at, updated_at) "
                    "VALUES (:id, :org, :em, 'AUDITOR', :th, NOW() + interval '2 days', NOW(), NOW())"
                ),
                [
                    {"id": inv_a, "org": org_a, "em": f"ia-{org_a.hex[:6]}@a.gov", "th": hash_token(f"ia-{org_a}")},
                    {"id": inv_b, "org": org_b, "em": f"ib-{org_b.hex[:6]}@b.gov", "th": hash_token(f"ib-{org_b}")},
                ],
            )
            await s.commit()

        # 2. Verify restricted role attributes
        async with AppSL() as s:
            role_row = (
                await s.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'bidguard_app'"))
            ).one()
            assert role_row[0] is False and role_row[1] is False

        # 3. Verify all 13 RLS tables under Org A context
        table_checks = [
            ("tenders", tender_a, tender_b, "title"),
            ("tender_clauses", clause_a, clause_b, "title"),
            ("bidders", bidder_a, bidder_b, "company_name"),
            ("bid_documents", doc_a, doc_b, "file_name"),
            ("document_chunks", chunk_a, chunk_b, "content"),
            ("compliance_evaluations", eval_a, eval_b, "status"),
            ("statutory_verification_records", stat_a, stat_b, "source_name"),
            ("recommendation_audit_records", rec_a, rec_b, "recommendation_summary"),
            ("audit_logs", audit_a, audit_b, None),  # UPDATE/DELETE blocked by 0005 trigger
            ("organization_invitations", inv_a, inv_b, "role_name"),
            ("users", user_a, user_b, "full_name"),
            ("user_roles", ur_a, ur_b, None),
            ("refresh_tokens", rt_a, rt_b, None),
        ]

        async with AppSL() as s:
            await s.execute(text("SELECT set_config('app.current_org_id', :org, true)"), {"org": str(org_a)})
            for tbl, id_a, id_b, upd_col in table_checks:
                cnt_a = (await s.execute(text(f"SELECT COUNT(*) FROM {tbl} WHERE id = :id"), {"id": id_a})).scalar()
                cnt_b = (await s.execute(text(f"SELECT COUNT(*) FROM {tbl} WHERE id = :id"), {"id": id_b})).scalar()
                assert cnt_a == 1, f"{tbl}: Org A should see own row"
                assert cnt_b == 0, f"{tbl}: Org A must NOT see Org B row"

                if upd_col:
                    res_upd = await s.execute(
                        text(f"UPDATE {tbl} SET {upd_col} = 'hacked' WHERE id = :id"), {"id": id_b}
                    )
                    assert res_upd.rowcount == 0, f"{tbl}: Org A must NOT update Org B row"

                if tbl != "audit_logs":
                    res_del = await s.execute(text(f"DELETE FROM {tbl} WHERE id = :id"), {"id": id_b})
                    assert res_del.rowcount == 0, f"{tbl}: Org A must NOT delete Org B row"

            # Cross-tenant INSERT with Org B's organization_id must fail with RLS WITH CHECK violation
            with pytest.raises(DBAPIError):
                await s.execute(
                    text(
                        "INSERT INTO tenders (id, organization_id, title, total_pages, extraction_status, next_clause_seq, created_at, updated_at) "
                        "VALUES (:id, :org_b, 'Evil Insert', 1, 'READY', '{}', NOW(), NOW())"
                    ),
                    {"id": uuid.uuid4(), "org_b": org_b},
                )
            await s.rollback()

        # 4. Verify connection-pool reuse (pool_size=1) does NOT leak Org A context after commit/rollback
        async with AppSL() as s:
            # No set_config called on this fresh checkout -> must fail closed (0 rows)
            leaked_cnt = (await s.execute(text("SELECT COUNT(*) FROM tenders WHERE id = :id"), {"id": tender_a})).scalar()
            assert leaked_cnt == 0, "Connection pool leaked previous tenant context!"

        # 5. Verify invalid tenant context fails closed
        async with AppSL() as s:
            await s.execute(text("SELECT set_config('app.current_org_id', 'not-a-uuid', true)"))
            with pytest.raises(DBAPIError):
                await s.execute(text("SELECT COUNT(*) FROM tenders"))
            await s.rollback()

        # 6. Verify SUPER_ADMIN explicit policy
        async with AppSL() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            sa_cnt = (
                await s.execute(text("SELECT COUNT(*) FROM tenders WHERE id IN (:a, :b)"), {"a": tender_a, "b": tender_b})
            ).scalar()
            assert sa_cnt == 2

        # 7. Workstream I: Verify audit_logs immutability trigger blocks UPDATE and DELETE under bidguard_app
        async with AppSL() as s:
            await s.execute(text("SELECT set_config('app.current_org_id', :org, true)"), {"org": str(org_a)})
            with pytest.raises(DBAPIError, match="audit_logs is append-only"):
                await s.execute(text("UPDATE audit_logs SET action = 'TAMPERED' WHERE id = :id"), {"id": audit_a})
            await s.rollback()

        async with AppSL() as s:
            await s.execute(text("SELECT set_config('app.current_org_id', :org, true)"), {"org": str(org_a)})
            with pytest.raises(DBAPIError, match="audit_logs is append-only"):
                await s.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": audit_a})
            await s.rollback()

    finally:
        await app_eng.dispose()
        await admin_eng.dispose()


@pytest.mark.anyio
async def test_postgres_concurrent_refresh_token_rotation():
    """Workstream F: Two genuinely concurrent PostgreSQL sessions sharing one refresh token."""
    admin_eng = create_async_engine(ADMIN_PG_URL, echo=False)
    app_eng = create_async_engine(APP_PG_URL, echo=False, pool_size=4, max_overflow=0)
    AdminSL = async_sessionmaker(admin_eng, class_=AsyncSession, expire_on_commit=False)
    AppSL = async_sessionmaker(app_eng, class_=AsyncSession, expire_on_commit=False)

    email = f"pg_race_{uuid.uuid4().hex[:8]}@gov.in"
    org_name = f"PG Race Org {uuid.uuid4().hex[:6]}"
    try:
        # Bootstrap org & user
        async with AdminSL() as s:
            _, raw_refresh, user, org, _, _ = await AuthService.register_organization_and_admin(
                email=email,
                password="StrongPgPassword123!",
                full_name="PG Race Officer",
                organization_name=org_name,
                organization_slug=None,
                domain=None,
                db=s,
            )

        async def attempt_refresh():
            async with AppSL() as s:
                try:
                    res = await AuthService.rotate_refresh_token(raw_refresh, s)
                    return ("OK", res[1])
                except HTTPException as exc:
                    return ("ERR", exc.status_code)

        res1, res2 = await asyncio.gather(attempt_refresh(), attempt_refresh())
        outcomes = sorted([res1[0], res2[0]])
        assert outcomes == ["ERR", "OK"], f"Expected exactly 1 OK and 1 ERR on concurrent PG refresh, got {(res1, res2)}"

        # Losing request triggered reuse detection -> entire token family revoked in DB
        async with AdminSL() as s:
            active_cnt = (
                await s.execute(
                    text("SELECT COUNT(*) FROM refresh_tokens WHERE user_id = :u AND revoked_at IS NULL"),
                    {"u": user.id},
                )
            ).scalar()
            assert active_cnt == 0, f"Expected all tokens in family revoked after concurrent reuse, found {active_cnt}"
    finally:
        await app_eng.dispose()
        await admin_eng.dispose()
