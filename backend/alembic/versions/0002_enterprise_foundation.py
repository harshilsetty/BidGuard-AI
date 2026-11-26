"""0002_enterprise_foundation

Revision ID: 0002_enterprise_foundation
Revises: 0001_initial_baseline
Create Date: 2026-11-24

Enterprise foundation models:
- organizations (Multi-tenancy)
- users (Authentication & Lifecycle)
- roles, permissions, user_roles, role_permissions (Granular RBAC)
- refresh_tokens (Rotating Hashed Session Tokens)
- audit_logs (Append-only immutable system & security audit trail)
- tenders.organization_id (Multi-tenant scoping)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0002_enterprise_foundation'
down_revision: Union[str, None] = '0001_initial_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = insp.get_table_names()

    # 1. organizations
    if 'organizations' not in existing_tables:
        op.create_table(
            'organizations',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('slug', sa.String(length=100), nullable=False),
            sa.Column('domain', sa.String(length=255), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_organizations_slug'), 'organizations', ['slug'], unique=True)
        op.create_index(op.f('ix_organizations_domain'), 'organizations', ['domain'], unique=False)

    # 2. users
    if 'users' not in existing_tables:
        op.create_table(
            'users',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('password_hash', sa.String(length=255), nullable=False),
            sa.Column('full_name', sa.String(length=255), nullable=False),
            sa.Column('organization_id', sa.UUID(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
        op.create_index(op.f('ix_users_organization_id'), 'users', ['organization_id'], unique=False)

    # 3. roles
    if 'roles' not in existing_tables:
        op.create_table(
            'roles',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('name', sa.String(length=50), nullable=False),
            sa.Column('description', sa.String(length=255), nullable=True),
            sa.Column('scope', sa.String(length=50), nullable=False, server_default='ORGANIZATION'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_roles_name'), 'roles', ['name'], unique=True)

    # 4. permissions
    if 'permissions' not in existing_tables:
        op.create_table(
            'permissions',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.String(length=255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_permissions_name'), 'permissions', ['name'], unique=True)

    # 5. role_permissions
    if 'role_permissions' not in existing_tables:
        op.create_table(
            'role_permissions',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('role_id', sa.UUID(), nullable=False),
            sa.Column('permission_id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('role_id', 'permission_id', name='uq_role_permission')
        )
        op.create_index(op.f('ix_role_permissions_role_id'), 'role_permissions', ['role_id'], unique=False)
        op.create_index(op.f('ix_role_permissions_permission_id'), 'role_permissions', ['permission_id'], unique=False)

    # 6. user_roles
    if 'user_roles' not in existing_tables:
        op.create_table(
            'user_roles',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('user_id', sa.UUID(), nullable=False),
            sa.Column('role_id', sa.UUID(), nullable=False),
            sa.Column('organization_id', sa.UUID(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'role_id', 'organization_id', name='uq_user_role_org')
        )
        op.create_index(op.f('ix_user_roles_user_id'), 'user_roles', ['user_id'], unique=False)
        op.create_index(op.f('ix_user_roles_role_id'), 'user_roles', ['role_id'], unique=False)
        op.create_index(op.f('ix_user_roles_organization_id'), 'user_roles', ['organization_id'], unique=False)

    # 7. refresh_tokens
    if 'refresh_tokens' not in existing_tables:
        op.create_table(
            'refresh_tokens',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('user_id', sa.UUID(), nullable=False),
            sa.Column('token_hash', sa.String(length=255), nullable=False),
            sa.Column('token_family_id', sa.UUID(), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('replaced_by_token_id', sa.UUID(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
        op.create_index(op.f('ix_refresh_tokens_token_hash'), 'refresh_tokens', ['token_hash'], unique=True)
        op.create_index(op.f('ix_refresh_tokens_token_family_id'), 'refresh_tokens', ['token_family_id'], unique=False)
        op.create_index(op.f('ix_refresh_tokens_expires_at'), 'refresh_tokens', ['expires_at'], unique=False)

    # 8. audit_logs
    if 'audit_logs' not in existing_tables:
        op.create_table(
            'audit_logs',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
            sa.Column('organization_id', sa.UUID(), nullable=True),
            sa.Column('user_id', sa.UUID(), nullable=True),
            sa.Column('action', sa.String(length=100), nullable=False),
            sa.Column('target_type', sa.String(length=100), nullable=False),
            sa.Column('target_id', sa.String(length=100), nullable=True),
            sa.Column('ip_address', sa.String(length=45), nullable=True),
            sa.Column('user_agent', sa.String(length=500), nullable=True),
            sa.Column('diff_json', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_audit_logs_timestamp'), 'audit_logs', ['timestamp'], unique=False)
        op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
        op.create_index(op.f('ix_audit_logs_target_type'), 'audit_logs', ['target_type'], unique=False)
        op.create_index(op.f('ix_audit_logs_target_id'), 'audit_logs', ['target_id'], unique=False)
        op.create_index(op.f('ix_audit_logs_organization_id'), 'audit_logs', ['organization_id'], unique=False)
        op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)

    # 9. Add organization_id to tenders if not already present
    if 'tenders' in existing_tables:
        tender_cols = [c['name'] for c in insp.get_columns('tenders')]
        if 'organization_id' not in tender_cols:
            op.add_column('tenders', sa.Column('organization_id', sa.UUID(), nullable=True))
            op.create_index(op.f('ix_tenders_organization_id'), 'tenders', ['organization_id'], unique=False)
            if bind.dialect.name == 'postgresql':
                op.create_foreign_key('fk_tenders_organization_id', 'tenders', 'organizations', ['organization_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.drop_constraint('fk_tenders_organization_id', 'tenders', type_='foreignkey')
    op.drop_index(op.f('ix_tenders_organization_id'), table_name='tenders')
    with op.batch_alter_table('tenders') as batch_op:
        batch_op.drop_column('organization_id')
    op.drop_table('audit_logs')
    op.drop_table('refresh_tokens')
    op.drop_table('user_roles')
    op.drop_table('role_permissions')
    op.drop_table('permissions')
    op.drop_table('roles')
    op.drop_table('users')
    op.drop_table('organizations')
