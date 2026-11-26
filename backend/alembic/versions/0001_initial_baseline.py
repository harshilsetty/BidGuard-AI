"""0001_initial_baseline

Revision ID: 0001_initial_baseline
Revises: 
Create Date: 2026-11-24

Baseline schema reflecting the initial BidGuard AI procurement compliance models:
tenders, tender_clauses, bidders, bid_documents, document_chunks,
compliance_evaluations, recommendation_audit_records, statutory_verification_records.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision: str = '0001_initial_baseline'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Baseline tables. When adopting an existing database, stamp 0001_initial_baseline.
    # Note: On PostgreSQL, enable extensions if needed
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'postgresql':
        op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
        op.execute('CREATE EXTENSION IF NOT EXISTS vector;')

    # 1. tenders
    op.create_table(
        'tenders',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('gem_tender_id', sa.String(length=100), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('file_name', sa.String(length=300), nullable=True),
        sa.Column('file_path', sa.String(length=1000), nullable=True),
        sa.Column('total_pages', sa.Integer(), nullable=False),
        sa.Column('extraction_status', sa.String(length=50), nullable=False),
        sa.Column('next_clause_seq', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tenders_gem_tender_id'), 'tenders', ['gem_tender_id'], unique=False)
    op.create_index(op.f('ix_tenders_extraction_status'), 'tenders', ['extraction_status'], unique=False)

    # 2. tender_clauses
    op.create_table(
        'tender_clauses',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tender_id', sa.UUID(), nullable=False),
        sa.Column('clause_code', sa.String(length=50), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('source_text', sa.Text(), nullable=False),
        sa.Column('is_mandatory', sa.Boolean(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('rule_config', sa.JSON(), nullable=True),
        sa.Column('is_confirmed', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tender_clauses_tender_id'), 'tender_clauses', ['tender_id'], unique=False)
    op.create_index(op.f('ix_tender_clauses_clause_code'), 'tender_clauses', ['clause_code'], unique=False)

    # 3. bidders
    op.create_table(
        'bidders',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tender_id', sa.UUID(), nullable=False),
        sa.Column('company_name', sa.String(length=300), nullable=False),
        sa.Column('overall_risk_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('final_status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bidders_tender_id'), 'bidders', ['tender_id'], unique=False)

    # 4. bid_documents
    op.create_table(
        'bid_documents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('bidder_id', sa.UUID(), nullable=False),
        sa.Column('file_name', sa.String(length=300), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('doc_type', sa.String(length=100), nullable=True),
        sa.Column('total_pages', sa.Integer(), nullable=False),
        sa.Column('empty_pages_count', sa.Integer(), nullable=False),
        sa.Column('extraction_status', sa.String(length=50), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['bidder_id'], ['bidders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bid_documents_bidder_id'), 'bid_documents', ['bidder_id'], unique=False)

    # 5. document_chunks
    op.create_table(
        'document_chunks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('bid_document_id', sa.UUID(), nullable=False),
        sa.Column('bidder_id', sa.UUID(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('start_char', sa.Integer(), nullable=True),
        sa.Column('end_char', sa.Integer(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', sa.JSON() if dialect != 'postgresql' else Vector(2048), nullable=True),
        sa.Column('extraction_method', sa.String(length=50), nullable=False),
        sa.Column('ocr_confidence', sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['bidder_id'], ['bidders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['bid_document_id'], ['bid_documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_chunks_bid_document_id'), 'document_chunks', ['bid_document_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_bidder_id'), 'document_chunks', ['bidder_id'], unique=False)

    # 6. compliance_evaluations
    op.create_table(
        'compliance_evaluations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('bidder_id', sa.UUID(), nullable=False),
        sa.Column('clause_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('confidence_score', sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column('claimed_value', sa.Text(), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('evidence_snippet', sa.Text(), nullable=True),
        sa.Column('evidence_page_number', sa.Integer(), nullable=True),
        sa.Column('evidence_chunk_id', sa.String(length=100), nullable=True),
        sa.Column('extraction_method', sa.String(length=50), nullable=True),
        sa.Column('ocr_confidence', sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column('rule_result', sa.JSON(), nullable=True),
        sa.Column('contradiction_detected', sa.Boolean(), nullable=False),
        sa.Column('contradiction_details', sa.Text(), nullable=True),
        sa.Column('risk_level', sa.String(length=20), nullable=False),
        sa.Column('override_status', sa.String(length=20), nullable=True),
        sa.Column('override_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['bidder_id'], ['bidders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['clause_id'], ['tender_clauses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_compliance_evaluations_bidder_id'), 'compliance_evaluations', ['bidder_id'], unique=False)
    op.create_index(op.f('ix_compliance_evaluations_clause_id'), 'compliance_evaluations', ['clause_id'], unique=False)

    # 7. recommendation_audit_records
    op.create_table(
        'recommendation_audit_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tender_id', sa.UUID(), nullable=False),
        sa.Column('bidder_id', sa.UUID(), nullable=False),
        sa.Column('evaluation_id', sa.UUID(), nullable=True),
        sa.Column('recommendation_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('recommendation_type', sa.String(length=50), nullable=False),
        sa.Column('recommendation_source', sa.String(length=50), nullable=False),
        sa.Column('score_at_recommendation', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('risk_at_recommendation', sa.String(length=50), nullable=False),
        sa.Column('recommendation_summary', sa.Text(), nullable=False),
        sa.Column('key_reasons', sa.JSON(), nullable=True),
        sa.Column('evidence_references', sa.JSON(), nullable=True),
        sa.Column('positive_findings', sa.JSON(), nullable=True),
        sa.Column('risk_findings', sa.JSON(), nullable=True),
        sa.Column('missing_evidence', sa.JSON(), nullable=True),
        sa.Column('contradictions', sa.JSON(), nullable=True),
        sa.Column('priority_actions', sa.JSON(), nullable=True),
        sa.Column('model_identifier', sa.String(length=100), nullable=False),
        sa.Column('officer_action', sa.String(length=50), nullable=True),
        sa.Column('officer_comment', sa.Text(), nullable=True),
        sa.Column('action_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('disclaimer', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['bidder_id'], ['bidders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['evaluation_id'], ['compliance_evaluations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recommendation_audit_records_bidder_id'), 'recommendation_audit_records', ['bidder_id'], unique=False)
    op.create_index(op.f('ix_recommendation_audit_records_evaluation_id'), 'recommendation_audit_records', ['evaluation_id'], unique=False)
    op.create_index(op.f('ix_recommendation_audit_records_recommendation_id'), 'recommendation_audit_records', ['recommendation_id'], unique=False)
    op.create_index(op.f('ix_recommendation_audit_records_tender_id'), 'recommendation_audit_records', ['tender_id'], unique=False)

    # 8. statutory_verification_records
    op.create_table(
        'statutory_verification_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tender_id', sa.UUID(), nullable=True),
        sa.Column('bidder_id', sa.UUID(), nullable=True),
        sa.Column('verification_id', sa.UUID(), nullable=False),
        sa.Column('authority', sa.String(length=50), nullable=False),
        sa.Column('source_name', sa.String(length=100), nullable=False),
        sa.Column('query_identifier', sa.String(length=100), nullable=False),
        sa.Column('identifier_type', sa.String(length=50), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.Column('connection_status', sa.String(length=50), nullable=False),
        sa.Column('verification_status', sa.String(length=50), nullable=False),
        sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('as_of_date', sa.Date(), nullable=True),
        sa.Column('data_payload', sa.JSON(), nullable=False),
        sa.Column('confidence_score', sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column('provenance_note', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('execution_time_ms', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['bidder_id'], ['bidders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_statutory_verification_records_tender_id'), 'statutory_verification_records', ['tender_id'], unique=False)
    op.create_index(op.f('ix_statutory_verification_records_bidder_id'), 'statutory_verification_records', ['bidder_id'], unique=False)
    op.create_index(op.f('ix_statutory_verification_records_verification_id'), 'statutory_verification_records', ['verification_id'], unique=False)
    op.create_index(op.f('ix_statutory_verification_records_authority'), 'statutory_verification_records', ['authority'], unique=False)


def downgrade() -> None:
    op.drop_table('statutory_verification_records')
    op.drop_table('recommendation_audit_records')
    op.drop_table('compliance_evaluations')
    op.drop_table('document_chunks')
    op.drop_table('bid_documents')
    op.drop_table('bidders')
    op.drop_table('tender_clauses')
    op.drop_table('tenders')
