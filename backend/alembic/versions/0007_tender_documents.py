"""0007_tender_documents

Revision ID: 0007_tender_documents
Revises: 0006_invitation_revocation
Create Date: 2026-11-26

Creates tender_documents table for multi-document tenders with per-tender
SHA-256 uniqueness and PostgreSQL FORCE ROW LEVEL SECURITY scoped through
the parent tender's organization_id.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0007_tender_documents'
down_revision: Union[str, None] = '0006_invitation_revocation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_ORG_EXPR = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"
SUPER_ADMIN_EXPR = "COALESCE(current_setting('app.is_super_admin', true), 'false') = 'true'"


def upgrade() -> None:
    op.create_table(
        'tender_documents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tender_id', sa.UUID(), nullable=False),
        sa.Column('document_role', sa.String(length=50), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('storage_path', sa.String(length=1000), nullable=False),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('sha256_hash', sa.String(length=64), nullable=False),
        sa.Column('total_pages', sa.Integer(), nullable=True),
        sa.Column('processing_status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tender_id', 'sha256_hash', name='uq_tender_documents_tender_sha256'),
    )
    op.create_index(op.f('ix_tender_documents_tender_id'), 'tender_documents', ['tender_id'], unique=False)
    op.create_index(op.f('ix_tender_documents_document_role'), 'tender_documents', ['document_role'], unique=False)
    op.create_index(op.f('ix_tender_documents_sha256_hash'), 'tender_documents', ['sha256_hash'], unique=False)
    op.create_index(op.f('ix_tender_documents_processing_status'), 'tender_documents', ['processing_status'], unique=False)

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        policy_expr = (
            f"{SUPER_ADMIN_EXPR} OR EXISTS ("
            f"SELECT 1 FROM tenders t WHERE t.id = tender_documents.tender_id "
            f"AND t.organization_id = {TENANT_ORG_EXPR})"
        )
        op.execute("ALTER TABLE tender_documents ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE tender_documents FORCE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_tender_documents ON tender_documents;")
        op.execute(
            f"CREATE POLICY tenant_isolation_tender_documents ON tender_documents "
            f"USING ({policy_expr}) WITH CHECK ({policy_expr});"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("DROP POLICY IF EXISTS tenant_isolation_tender_documents ON tender_documents;")
        op.execute("ALTER TABLE tender_documents NO FORCE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE tender_documents DISABLE ROW LEVEL SECURITY;")

    op.drop_index(op.f('ix_tender_documents_processing_status'), table_name='tender_documents')
    op.drop_index(op.f('ix_tender_documents_sha256_hash'), table_name='tender_documents')
    op.drop_index(op.f('ix_tender_documents_document_role'), table_name='tender_documents')
    op.drop_index(op.f('ix_tender_documents_tender_id'), table_name='tender_documents')
    op.drop_table('tender_documents')
