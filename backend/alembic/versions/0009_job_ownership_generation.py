"""0009_job_ownership_generation

Revision ID: 0009_job_ownership_generation
Revises: 0008_tender_jobs_and_pages
Create Date: 2026-11-27

Adds monotonic ownership_generation fencing token to tender_processing_jobs.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0009_job_ownership_generation'
down_revision: Union[str, None] = '0008_tender_jobs_and_pages'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tender_processing_jobs',
        sa.Column('ownership_generation', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('tender_processing_jobs', 'ownership_generation')
