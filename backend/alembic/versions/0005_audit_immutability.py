"""0005_audit_immutability

Revision ID: 0005_audit_immutability
Revises: 0004_comprehensive_rls
Create Date: 2026-11-25

Enforces database-level append-only immutability on audit_logs in PostgreSQL
via BEFORE UPDATE OR DELETE trigger preventing historical tampering.
"""
from typing import Sequence, Union
from alembic import op

revision: str = '0005_audit_immutability'
down_revision: Union[str, None] = '0004_comprehensive_rls'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON audit_logs;")
        op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_mutation();")
