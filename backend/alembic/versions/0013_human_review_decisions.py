"""0013_human_review_decisions

Revision ID: 0013_human_review_decisions
Revises: 0012_audit_immutability_sync
Create Date: 2026-11-27

Adds optimistic-concurrency review_version and assignment columns to reviewable
objects, creates append-only review_decisions table with immutability trigger,
and enables PostgreSQL FORCE ROW LEVEL SECURITY.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0013_human_review_decisions'
down_revision: Union[str, None] = '0012_audit_immutability_sync'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_ORG_EXPR = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"
SUPER_ADMIN_EXPR = "COALESCE(current_setting('app.is_super_admin', true), 'false') = 'true'"


def upgrade() -> None:
    op.add_column('tender_requirements', sa.Column('review_version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('tender_requirements', sa.Column('assigned_reviewer_id', sa.UUID(), nullable=True))
    op.add_column('tender_requirements', sa.Column('last_reviewed_by_user_id', sa.UUID(), nullable=True))
    op.add_column('tender_requirements', sa.Column('last_reviewed_at', sa.DateTime(timezone=True), nullable=True))

    op.add_column('tender_requirement_conflicts', sa.Column('review_version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('tender_requirement_conflicts', sa.Column('assigned_reviewer_id', sa.UUID(), nullable=True))

    op.add_column('tender_requirement_evidence', sa.Column('review_version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('tender_requirement_evidence', sa.Column('assigned_reviewer_id', sa.UUID(), nullable=True))
    op.add_column('tender_requirement_evidence', sa.Column('reviewed_by_user_id', sa.UUID(), nullable=True))
    op.add_column('tender_requirement_evidence', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        'review_decisions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=True),
        sa.Column('tender_id', sa.UUID(), nullable=False),
        sa.Column('object_type', sa.String(length=32), nullable=False),
        sa.Column('object_id', sa.UUID(), nullable=False),
        sa.Column('reviewer_user_id', sa.UUID(), nullable=True),
        sa.Column('decision_type', sa.String(length=32), nullable=False),
        sa.Column('previous_status', sa.String(length=32), nullable=False),
        sa.Column('new_status', sa.String(length=32), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('object_version', sa.Integer(), nullable=False),
        sa.Column('source_document_sha256', sa.String(length=64), nullable=True),
        sa.Column('assigned_to_user_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewer_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_review_decisions_organization_id'), 'review_decisions', ['organization_id'], unique=False)
    op.create_index(op.f('ix_review_decisions_tender_id'), 'review_decisions', ['tender_id'], unique=False)
    op.create_index(op.f('ix_review_decisions_object_type'), 'review_decisions', ['object_type'], unique=False)
    op.create_index(op.f('ix_review_decisions_object_id'), 'review_decisions', ['object_id'], unique=False)
    op.create_index(op.f('ix_review_decisions_reviewer_user_id'), 'review_decisions', ['reviewer_user_id'], unique=False)

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute(
            """
            CREATE OR REPLACE FUNCTION prevent_review_decision_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'review_decisions is append-only: % operations are forbidden', TG_OP;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_review_decisions_immutable ON review_decisions;")
        op.execute(
            """
            CREATE TRIGGER trg_review_decisions_immutable
            BEFORE UPDATE OR DELETE ON review_decisions
            FOR EACH ROW
            EXECUTE FUNCTION prevent_review_decision_mutation();
            """
        )
        policy = (
            f"{SUPER_ADMIN_EXPR} OR EXISTS ("
            f"SELECT 1 FROM tenders t WHERE t.id = review_decisions.tender_id "
            f"AND t.organization_id = {TENANT_ORG_EXPR})"
        )
        op.execute("ALTER TABLE review_decisions ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE review_decisions FORCE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_review_decisions ON review_decisions;")
        op.execute(
            f"CREATE POLICY tenant_isolation_review_decisions ON review_decisions "
            f"USING ({policy}) WITH CHECK ({policy});"
        )
        op.execute(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bidguard_app') THEN "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON review_decisions TO bidguard_app; "
            "END IF; END $$;"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("DROP POLICY IF EXISTS tenant_isolation_review_decisions ON review_decisions;")
        op.execute("DROP TRIGGER IF EXISTS trg_review_decisions_immutable ON review_decisions;")
        op.execute("DROP FUNCTION IF EXISTS prevent_review_decision_mutation();")
    op.drop_table('review_decisions')
    op.drop_column('tender_requirement_evidence', 'reviewed_at')
    op.drop_column('tender_requirement_evidence', 'reviewed_by_user_id')
    op.drop_column('tender_requirement_evidence', 'assigned_reviewer_id')
    op.drop_column('tender_requirement_evidence', 'review_version')
    op.drop_column('tender_requirement_conflicts', 'assigned_reviewer_id')
    op.drop_column('tender_requirement_conflicts', 'review_version')
    op.drop_column('tender_requirements', 'last_reviewed_at')
    op.drop_column('tender_requirements', 'last_reviewed_by_user_id')
    op.drop_column('tender_requirements', 'assigned_reviewer_id')
    op.drop_column('tender_requirements', 'review_version')
