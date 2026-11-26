"""0006_invitation_revocation

Revision ID: 0006_invitation_revocation
Revises: 0005_audit_immutability
Create Date: 2026-11-26

Adds revoked_at column to organization_invitations to support explicit
server-side invitation revocation and resend invalidation.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0006_invitation_revocation'
down_revision: Union[str, None] = '0005_audit_immutability'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'organization_invitations',
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('organization_invitations', 'revoked_at')
