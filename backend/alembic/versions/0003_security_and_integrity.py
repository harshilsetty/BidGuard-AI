"""0003_security_and_integrity

Revision ID: 0003_security_and_integrity
Revises: 0002_enterprise_foundation
Create Date: 2026-11-25

Forward remediation migration:
- Creates organization_invitations (single-use expiring invitations)
- Adds document_chunks.embedding_model for embedding-space consistency
- Ensures SQLite tenders.organization_id foreign key constraint via batch mode
- Enables PostgreSQL Row-Level Security (RLS) policies for tenant isolation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0003_security_and_integrity'
down_revision: Union[str, None] = '0002_enterprise_foundation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = insp.get_table_names()

    # 1. organization_invitations
    if 'organization_invitations' not in existing_tables:
        op.create_table(
            'organization_invitations',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('organization_id', sa.UUID(), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('role_name', sa.String(length=50), nullable=False),
            sa.Column('token_hash', sa.String(length=255), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('invited_by_user_id', sa.UUID(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['invited_by_user_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_organization_invitations_organization_id'), 'organization_invitations', ['organization_id'], unique=False)
        op.create_index(op.f('ix_organization_invitations_email'), 'organization_invitations', ['email'], unique=False)
        op.create_index(op.f('ix_organization_invitations_token_hash'), 'organization_invitations', ['token_hash'], unique=True)
        op.create_index(op.f('ix_organization_invitations_expires_at'), 'organization_invitations', ['expires_at'], unique=False)

    # 2. document_chunks.embedding_model
    if 'document_chunks' in existing_tables:
        chunk_cols = [c['name'] for c in insp.get_columns('document_chunks')]
        if 'embedding_model' not in chunk_cols:
            op.add_column('document_chunks', sa.Column('embedding_model', sa.String(length=100), nullable=True))

    # 3. Ensure SQLite tenders.organization_id FK exists via batch mode
    if bind.dialect.name == 'sqlite' and 'tenders' in existing_tables:
        fks = insp.get_foreign_keys('tenders')
        has_org_fk = any('organization_id' in fk.get('constrained_columns', []) for fk in fks)
        if not has_org_fk:
            with op.batch_alter_table('tenders') as batch_op:
                batch_op.create_foreign_key(
                    'fk_tenders_organization_id',
                    'organizations',
                    ['organization_id'],
                    ['id'],
                    ondelete='SET NULL',
                )

    # 4. PostgreSQL Row-Level Security (RLS) for multi-tenant tables
    if bind.dialect.name == 'postgresql':
        rls_tables = [
            'tenders',
            'audit_logs',
            'organization_invitations',
        ]
        for tbl in rls_tables:
            op.execute(f'ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;')
            op.execute(f'ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;')
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation_{tbl} ON {tbl};')
            op.execute(
                f"""
                CREATE POLICY tenant_isolation_{tbl} ON {tbl}
                USING (
                    COALESCE(current_setting('app.is_super_admin', true), 'false') = 'true'
                    OR organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
                )
                WITH CHECK (
                    COALESCE(current_setting('app.is_super_admin', true), 'false') = 'true'
                    OR organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
                );
                """
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        for tbl in ['tenders', 'audit_logs', 'organization_invitations']:
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation_{tbl} ON {tbl};')
            op.execute(f'ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;')
            op.execute(f'ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;')

    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('tenders') as batch_op:
            batch_op.drop_constraint('fk_tenders_organization_id', type_='foreignkey')

    op.drop_column('document_chunks', 'embedding_model')
    op.drop_table('organization_invitations')
