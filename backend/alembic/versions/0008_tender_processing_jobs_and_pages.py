"""0008_tender_processing_jobs_and_pages

Revision ID: 0008_tender_processing_jobs_and_pages
Revises: 0007_tender_documents
Create Date: 2026-11-26

Creates tender_processing_jobs and tender_document_pages tables with
indexes, unique constraints, and PostgreSQL FORCE ROW LEVEL SECURITY.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0008_tender_jobs_and_pages'
down_revision: Union[str, None] = '0007_tender_documents'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_ORG_EXPR = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"
SUPER_ADMIN_EXPR = "COALESCE(current_setting('app.is_super_admin', true), 'false') = 'true'"


def upgrade() -> None:
    op.create_table(
        'tender_processing_jobs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tender_id', sa.UUID(), nullable=False),
        sa.Column('tender_document_id', sa.UUID(), nullable=False),
        sa.Column('job_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('max_retries', sa.Integer(), nullable=False),
        sa.Column('progress_pct', sa.Integer(), nullable=False),
        sa.Column('current_stage', sa.String(length=64), nullable=False),
        sa.Column('error_code', sa.String(length=64), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('worker_id', sa.String(length=128), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tender_document_id'], ['tender_documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tender_processing_jobs_tender_id'), 'tender_processing_jobs', ['tender_id'], unique=False)
    op.create_index(op.f('ix_tender_processing_jobs_tender_document_id'), 'tender_processing_jobs', ['tender_document_id'], unique=False)
    op.create_index(op.f('ix_tender_processing_jobs_status'), 'tender_processing_jobs', ['status'], unique=False)
    op.create_index(op.f('ix_tender_processing_jobs_idempotency_key'), 'tender_processing_jobs', ['idempotency_key'], unique=False)
    op.create_index(op.f('ix_tender_processing_jobs_lease_expires_at'), 'tender_processing_jobs', ['lease_expires_at'], unique=False)

    op.create_table(
        'tender_document_pages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tender_document_id', sa.UUID(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('extracted_text', sa.Text(), nullable=False),
        sa.Column('word_count', sa.Integer(), nullable=False),
        sa.Column('extraction_method', sa.String(length=50), nullable=False),
        sa.Column('ocr_confidence', sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column('extraction_status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tender_document_id'], ['tender_documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tender_document_id', 'page_number', name='uq_tender_document_pages_doc_page'),
    )
    op.create_index(op.f('ix_tender_document_pages_tender_document_id'), 'tender_document_pages', ['tender_document_id'], unique=False)

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute(
            "CREATE UNIQUE INDEX uq_active_job_per_doc_type ON tender_processing_jobs (idempotency_key) "
            "WHERE status IN ('QUEUED', 'RUNNING', 'RETRY_WAIT');"
        )

        jobs_policy = (
            f"{SUPER_ADMIN_EXPR} OR EXISTS ("
            f"SELECT 1 FROM tenders t WHERE t.id = tender_processing_jobs.tender_id "
            f"AND t.organization_id = {TENANT_ORG_EXPR})"
        )
        op.execute("ALTER TABLE tender_processing_jobs ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE tender_processing_jobs FORCE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_tender_processing_jobs ON tender_processing_jobs;")
        op.execute(
            f"CREATE POLICY tenant_isolation_tender_processing_jobs ON tender_processing_jobs "
            f"USING ({jobs_policy}) WITH CHECK ({jobs_policy});"
        )

        pages_policy = (
            f"{SUPER_ADMIN_EXPR} OR EXISTS ("
            f"SELECT 1 FROM tender_documents td JOIN tenders t ON t.id = td.tender_id "
            f"WHERE td.id = tender_document_pages.tender_document_id "
            f"AND t.organization_id = {TENANT_ORG_EXPR})"
        )
        op.execute("ALTER TABLE tender_document_pages ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE tender_document_pages FORCE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_tender_document_pages ON tender_document_pages;")
        op.execute(
            f"CREATE POLICY tenant_isolation_tender_document_pages ON tender_document_pages "
            f"USING ({pages_policy}) WITH CHECK ({pages_policy});"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("DROP POLICY IF EXISTS tenant_isolation_tender_document_pages ON tender_document_pages;")
        op.execute("ALTER TABLE tender_document_pages NO FORCE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE tender_document_pages DISABLE ROW LEVEL SECURITY;")

        op.execute("DROP POLICY IF EXISTS tenant_isolation_tender_processing_jobs ON tender_processing_jobs;")
        op.execute("ALTER TABLE tender_processing_jobs NO FORCE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE tender_processing_jobs DISABLE ROW LEVEL SECURITY;")
        op.execute("DROP INDEX IF EXISTS uq_active_job_per_doc_type;")

    op.drop_index(op.f('ix_tender_document_pages_tender_document_id'), table_name='tender_document_pages')
    op.drop_table('tender_document_pages')

    op.drop_index(op.f('ix_tender_processing_jobs_lease_expires_at'), table_name='tender_processing_jobs')
    op.drop_index(op.f('ix_tender_processing_jobs_idempotency_key'), table_name='tender_processing_jobs')
    op.drop_index(op.f('ix_tender_processing_jobs_status'), table_name='tender_processing_jobs')
    op.drop_index(op.f('ix_tender_processing_jobs_tender_document_id'), table_name='tender_processing_jobs')
    op.drop_index(op.f('ix_tender_processing_jobs_tender_id'), table_name='tender_processing_jobs')
    op.drop_table('tender_processing_jobs')
