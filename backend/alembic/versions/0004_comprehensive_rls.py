"""0004_comprehensive_rls

Revision ID: 0004_comprehensive_rls
Revises: 0003_security_and_integrity
Create Date: 2026-11-25

Comprehensive PostgreSQL Row-Level Security (RLS) coverage across all
tenant-owned and user-owned tables:
- tender_clauses, bidders, bid_documents, document_chunks
- compliance_evaluations, statutory_verification_records, recommendation_audit_records
- users, user_roles, refresh_tokens
"""
from typing import Sequence, Union
from alembic import op

revision: str = '0004_comprehensive_rls'
down_revision: Union[str, None] = '0003_security_and_integrity'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_ORG_EXPR = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"
SUPER_ADMIN_EXPR = "COALESCE(current_setting('app.is_super_admin', true), 'false') = 'true'"
AUTH_LOOKUP_EXPR = "COALESCE(current_setting('app.auth_lookup', true), 'false') = 'true'"

POLICIES = {
    "tender_clauses": (
        f"{SUPER_ADMIN_EXPR} OR EXISTS ("
        f"SELECT 1 FROM tenders t WHERE t.id = tender_clauses.tender_id AND t.organization_id = {TENANT_ORG_EXPR})"
    ),
    "bidders": (
        f"{SUPER_ADMIN_EXPR} OR EXISTS ("
        f"SELECT 1 FROM tenders t WHERE t.id = bidders.tender_id AND t.organization_id = {TENANT_ORG_EXPR})"
    ),
    "bid_documents": (
        f"{SUPER_ADMIN_EXPR} OR EXISTS ("
        f"SELECT 1 FROM bidders b JOIN tenders t ON t.id = b.tender_id "
        f"WHERE b.id = bid_documents.bidder_id AND t.organization_id = {TENANT_ORG_EXPR})"
    ),
    "document_chunks": (
        f"{SUPER_ADMIN_EXPR} OR EXISTS ("
        f"SELECT 1 FROM bidders b JOIN tenders t ON t.id = b.tender_id "
        f"WHERE b.id = document_chunks.bidder_id AND t.organization_id = {TENANT_ORG_EXPR})"
    ),
    "compliance_evaluations": (
        f"{SUPER_ADMIN_EXPR} OR EXISTS ("
        f"SELECT 1 FROM bidders b JOIN tenders t ON t.id = b.tender_id "
        f"WHERE b.id = compliance_evaluations.bidder_id AND t.organization_id = {TENANT_ORG_EXPR})"
    ),
    "statutory_verification_records": (
        f"{SUPER_ADMIN_EXPR} OR EXISTS ("
        f"SELECT 1 FROM tenders t WHERE t.id = statutory_verification_records.tender_id AND t.organization_id = {TENANT_ORG_EXPR})"
    ),
    "recommendation_audit_records": (
        f"{SUPER_ADMIN_EXPR} OR EXISTS ("
        f"SELECT 1 FROM tenders t WHERE t.id = recommendation_audit_records.tender_id AND t.organization_id = {TENANT_ORG_EXPR})"
    ),
    "users": (
        f"{SUPER_ADMIN_EXPR} OR {AUTH_LOOKUP_EXPR} OR organization_id = {TENANT_ORG_EXPR}"
    ),
    "user_roles": (
        f"{SUPER_ADMIN_EXPR} OR {AUTH_LOOKUP_EXPR} OR organization_id = {TENANT_ORG_EXPR}"
    ),
    "refresh_tokens": (
        f"{SUPER_ADMIN_EXPR} OR {AUTH_LOOKUP_EXPR} OR EXISTS ("
        f"SELECT 1 FROM users u WHERE u.id = refresh_tokens.user_id AND u.organization_id = {TENANT_ORG_EXPR})"
    ),
}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        for tbl, expr in POLICIES.items():
            op.execute(f'ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;')
            op.execute(f'ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;')
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation_{tbl} ON {tbl};')
            op.execute(
                f'CREATE POLICY tenant_isolation_{tbl} ON {tbl} '
                f'USING ({expr}) WITH CHECK ({expr});'
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        for tbl in POLICIES:
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation_{tbl} ON {tbl};')
            op.execute(f'ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;')
            op.execute(f'ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;')
