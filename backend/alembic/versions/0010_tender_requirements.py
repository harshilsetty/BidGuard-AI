"""0010_tender_requirements

Revision ID: 0010_tender_requirements
Revises: 0009_job_ownership_generation
Create Date: 2026-11-27

Creates tender_requirements table with indexes, PostgreSQL FORCE ROW LEVEL SECURITY,
and adds extracted_count / extraction_version to tender_processing_jobs.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0010_tender_requirements'
down_revision: Union[str, None] = '0009_job_ownership_generation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_ORG_EXPR = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"
SUPER_ADMIN_EXPR = "COALESCE(current_setting('app.is_super_admin', true), 'false') = 'true'"


def upgrade() -> None:
    op.add_column(
        'tender_processing_jobs',
        sa.Column('extracted_count', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'tender_processing_jobs',
        sa.Column('extraction_version', sa.Integer(), nullable=False, server_default='1'),
    )

    op.create_table(
        'tender_requirements',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tender_id', sa.UUID(), nullable=False),
        sa.Column('source_document_id', sa.UUID(), nullable=False),
        sa.Column('processing_job_id', sa.UUID(), nullable=True),
        sa.Column('requirement_code', sa.String(length=50), nullable=False),
        sa.Column('extraction_version', sa.Integer(), nullable=False),
        sa.Column('source_page_number', sa.Integer(), nullable=False),
        sa.Column('source_page_range', sa.String(length=32), nullable=True),
        sa.Column('source_section', sa.String(length=200), nullable=True),
        sa.Column('source_text', sa.Text(), nullable=False),
        sa.Column('source_quote_verified', sa.Boolean(), nullable=False),
        sa.Column('normalized_statement', sa.Text(), nullable=False),
        sa.Column('explanatory_interpretation', sa.Text(), nullable=False),
        sa.Column('primary_category', sa.String(length=32), nullable=False),
        sa.Column('secondary_categories', sa.JSON(), nullable=False),
        sa.Column('requirement_type', sa.String(length=50), nullable=False),
        sa.Column('mandatory_status', sa.String(length=20), nullable=False),
        sa.Column('expected_document_or_evidence', sa.Text(), nullable=True),
        sa.Column('expected_action_by_bidder', sa.Text(), nullable=True),
        sa.Column('numeric_value', sa.String(length=64), nullable=True),
        sa.Column('unit', sa.String(length=64), nullable=True),
        sa.Column('currency', sa.String(length=16), nullable=True),
        sa.Column('period_or_validity', sa.String(length=128), nullable=True),
        sa.Column('conditions_and_exceptions', sa.Text(), nullable=True),
        sa.Column('extraction_method', sa.String(length=50), nullable=False),
        sa.Column('model_provider', sa.String(length=64), nullable=False),
        sa.Column('model_version', sa.String(length=128), nullable=True),
        sa.Column('extraction_confidence', sa.Float(), nullable=False),
        sa.Column('review_status', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_document_id'], ['tender_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['processing_job_id'], ['tender_processing_jobs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tender_requirements_tender_id'), 'tender_requirements', ['tender_id'], unique=False)
    op.create_index(op.f('ix_tender_requirements_source_document_id'), 'tender_requirements', ['source_document_id'], unique=False)
    op.create_index(op.f('ix_tender_requirements_processing_job_id'), 'tender_requirements', ['processing_job_id'], unique=False)
    op.create_index(op.f('ix_tender_requirements_requirement_code'), 'tender_requirements', ['requirement_code'], unique=False)
    op.create_index(op.f('ix_tender_requirements_extraction_version'), 'tender_requirements', ['extraction_version'], unique=False)
    op.create_index(op.f('ix_tender_requirements_primary_category'), 'tender_requirements', ['primary_category'], unique=False)
    op.create_index(op.f('ix_tender_requirements_mandatory_status'), 'tender_requirements', ['mandatory_status'], unique=False)
    op.create_index(op.f('ix_tender_requirements_review_status'), 'tender_requirements', ['review_status'], unique=False)

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        req_policy = (
            f"{SUPER_ADMIN_EXPR} OR EXISTS ("
            f"SELECT 1 FROM tenders t WHERE t.id = tender_requirements.tender_id "
            f"AND t.organization_id = {TENANT_ORG_EXPR})"
        )
        op.execute("ALTER TABLE tender_requirements ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE tender_requirements FORCE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_tender_requirements ON tender_requirements;")
        op.execute(
            f"CREATE POLICY tenant_isolation_tender_requirements ON tender_requirements "
            f"USING ({req_policy}) WITH CHECK ({req_policy});"
        )
        op.execute(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bidguard_app') THEN "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON tender_requirements TO bidguard_app; "
            "END IF; END $$;"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("DROP POLICY IF EXISTS tenant_isolation_tender_requirements ON tender_requirements;")
    op.drop_table('tender_requirements')
    op.drop_column('tender_processing_jobs', 'extraction_version')
    op.drop_column('tender_processing_jobs', 'extracted_count')
