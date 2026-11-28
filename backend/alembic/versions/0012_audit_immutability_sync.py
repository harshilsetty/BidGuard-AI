"""0012_audit_immutability_sync

Revision ID: 0012_audit_immutability_sync
Revises: 0011_prov_conflicts_evidence
Create Date: 2026-11-27

Reconciles audit_logs append-only immutability trigger, trigger function, and
FORCE ROW LEVEL SECURITY across all environments (fixing gem_compliance drift).
"""
from typing import Sequence, Union
from alembic import op

revision: str = '0012_audit_immutability_sync'
down_revision: Union[str, None] = '0011_prov_conflicts_evidence'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_ORG_EXPR = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"
SUPER_ADMIN_EXPR = "COALESCE(current_setting('app.is_super_admin', true), 'false') = 'true'"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute(
            """
            CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'audit_logs is append-only: % operations are forbidden', TG_OP;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON audit_logs;")
        op.execute(
            """
            CREATE TRIGGER trg_audit_logs_immutable
            BEFORE UPDATE OR DELETE ON audit_logs
            FOR EACH ROW
            EXECUTE FUNCTION prevent_audit_log_mutation();
            """
        )

        audit_policy = (
            f"{SUPER_ADMIN_EXPR} OR "
            f"organization_id = {TENANT_ORG_EXPR}"
        )
        op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_audit_logs ON audit_logs;")
        op.execute(
            f"CREATE POLICY tenant_isolation_audit_logs ON audit_logs "
            f"USING ({audit_policy}) WITH CHECK ({audit_policy});"
        )
        op.execute(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bidguard_app') THEN "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON audit_logs TO bidguard_app; "
            "END IF; END $$;"
        )


def downgrade() -> None:
    # Reconciliation migration preserves 0005 immutability on downgrade.
    pass
