"""0011_provenance_conflicts_evidence

Revision ID: 0011_prov_conflicts_evidence
Revises: 0010_tender_requirements
Create Date: 2026-11-27

Adds Phase 2.0D document relationship metadata, requirement provenance fields,
tender_requirement_sources, tender_requirement_conflicts, tender_requirement_evidence,
and PostgreSQL FORCE ROW LEVEL SECURITY policies.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0011_prov_conflicts_evidence'
down_revision: Union[str, None] = '0010_tender_requirements'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_ORG_EXPR = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"
SUPER_ADMIN_EXPR = "COALESCE(current_setting('app.is_super_admin', true), 'false') = 'true'"


def upgrade() -> None:
    op.add_column('tender_documents', sa.Column('document_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tender_documents', sa.Column('issue_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tender_documents', sa.Column('reference_number', sa.String(length=128), nullable=True))
    op.add_column('tender_documents', sa.Column('related_document_id', sa.UUID(), nullable=True))
    op.add_column('tender_documents', sa.Column('applicability_scope', sa.String(length=200), nullable=True))
    op.add_column('tender_documents', sa.Column('revision_info', sa.String(length=128), nullable=True))
    op.create_foreign_key(
        'fk_tender_documents_related_document_id',
        'tender_documents',
        'tender_documents',
        ['related_document_id'],
        ['id'],
        ondelete='SET NULL',
    )

    op.add_column(
        'tender_requirements',
        sa.Column('provenance_status', sa.String(length=32), nullable=False, server_default='UNVERIFIED'),
    )
    op.add_column(
        'tender_requirements',
        sa.Column('source_document_sha256', sa.String(length=64), nullable=True),
    )

    op.create_table(
        'tender_requirement_sources',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tender_id', sa.UUID(), nullable=False),
        sa.Column('requirement_id', sa.UUID(), nullable=False),
        sa.Column('source_document_id', sa.UUID(), nullable=False),
        sa.Column('source_role', sa.String(length=40), nullable=False),
        sa.Column('source_page_number', sa.Integer(), nullable=False),
        sa.Column('source_section', sa.String(length=200), nullable=True),
        sa.Column('source_text', sa.Text(), nullable=False),
        sa.Column('verification_status', sa.String(length=32), nullable=False),
        sa.Column('source_document_sha256', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requirement_id'], ['tender_requirements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_document_id'], ['tender_documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tender_requirement_sources_tender_id'), 'tender_requirement_sources', ['tender_id'], unique=False)
    op.create_index(op.f('ix_tender_requirement_sources_requirement_id'), 'tender_requirement_sources', ['requirement_id'], unique=False)
    op.create_index(op.f('ix_tender_requirement_sources_source_document_id'), 'tender_requirement_sources', ['source_document_id'], unique=False)

    op.create_table(
        'tender_requirement_conflicts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tender_id', sa.UUID(), nullable=False),
        sa.Column('requirement_a_id', sa.UUID(), nullable=False),
        sa.Column('requirement_b_id', sa.UUID(), nullable=False),
        sa.Column('conflict_type', sa.String(length=40), nullable=False),
        sa.Column('relationship_type', sa.String(length=40), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('scope_summary', sa.String(length=255), nullable=True),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('reviewed_by_user_id', sa.UUID(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requirement_a_id'], ['tender_requirements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requirement_b_id'], ['tender_requirements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tender_requirement_conflicts_tender_id'), 'tender_requirement_conflicts', ['tender_id'], unique=False)
    op.create_index(op.f('ix_tender_requirement_conflicts_conflict_type'), 'tender_requirement_conflicts', ['conflict_type'], unique=False)
    op.create_index(op.f('ix_tender_requirement_conflicts_severity'), 'tender_requirement_conflicts', ['severity'], unique=False)
    op.create_index(op.f('ix_tender_requirement_conflicts_status'), 'tender_requirement_conflicts', ['status'], unique=False)

    op.create_table(
        'tender_requirement_evidence',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tender_id', sa.UUID(), nullable=False),
        sa.Column('requirement_id', sa.UUID(), nullable=False),
        sa.Column('evidence_type', sa.String(length=64), nullable=False),
        sa.Column('expected_document_name', sa.String(length=255), nullable=False),
        sa.Column('evidence_purpose', sa.Text(), nullable=False),
        sa.Column('is_mandatory', sa.Boolean(), nullable=False),
        sa.Column('source_passage', sa.Text(), nullable=False),
        sa.Column('mapping_method', sa.String(length=50), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('mapping_status', sa.String(length=24), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requirement_id'], ['tender_requirements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tender_requirement_evidence_tender_id'), 'tender_requirement_evidence', ['tender_id'], unique=False)
    op.create_index(op.f('ix_tender_requirement_evidence_requirement_id'), 'tender_requirement_evidence', ['requirement_id'], unique=False)
    op.create_index(op.f('ix_tender_requirement_evidence_evidence_type'), 'tender_requirement_evidence', ['evidence_type'], unique=False)
    op.create_index(op.f('ix_tender_requirement_evidence_mapping_status'), 'tender_requirement_evidence', ['mapping_status'], unique=False)

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        for tbl in ('tender_requirement_sources', 'tender_requirement_conflicts', 'tender_requirement_evidence'):
            policy = (
                f"{SUPER_ADMIN_EXPR} OR EXISTS ("
                f"SELECT 1 FROM tenders t WHERE t.id = {tbl}.tender_id "
                f"AND t.organization_id = {TENANT_ORG_EXPR})"
            )
            op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{tbl} ON {tbl};")
            op.execute(
                f"CREATE POLICY tenant_isolation_{tbl} ON {tbl} "
                f"USING ({policy}) WITH CHECK ({policy});"
            )
            op.execute(
                "DO $$ BEGIN "
                "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bidguard_app') THEN "
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tbl} TO bidguard_app; "
                "END IF; END $$;"
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        for tbl in ('tender_requirement_evidence', 'tender_requirement_conflicts', 'tender_requirement_sources'):
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{tbl} ON {tbl};")
    op.drop_table('tender_requirement_evidence')
    op.drop_table('tender_requirement_conflicts')
    op.drop_table('tender_requirement_sources')
    op.drop_column('tender_requirements', 'source_document_sha256')
    op.drop_column('tender_requirements', 'provenance_status')
    op.drop_constraint('fk_tender_documents_related_document_id', 'tender_documents', type_='foreignkey')
    op.drop_column('tender_documents', 'revision_info')
    op.drop_column('tender_documents', 'applicability_scope')
    op.drop_column('tender_documents', 'related_document_id')
    op.drop_column('tender_documents', 'reference_number')
    op.drop_column('tender_documents', 'issue_date')
    op.drop_column('tender_documents', 'document_date')
