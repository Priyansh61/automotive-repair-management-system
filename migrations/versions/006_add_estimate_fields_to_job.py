"""Add estimate fields to job table

Revision ID: 006
Revises: 005
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('job', sa.Column('is_estimate', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('job', sa.Column('estimate_approved', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('job', sa.Column('contingency_amount', sa.Numeric(12, 2), nullable=False, server_default='0'))
    op.add_column('job', sa.Column('contingency_note', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('job', 'contingency_note')
    op.drop_column('job', 'contingency_amount')
    op.drop_column('job', 'estimate_approved')
    op.drop_column('job', 'is_estimate')
