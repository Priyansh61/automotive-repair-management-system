"""Add vehicle table, job_complaint table, and job columns

Revision ID: 005
Revises: 004
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'vehicle',
        sa.Column('vehicle_id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenant.tenant_id'), nullable=True, index=True),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customer.customer_id'), nullable=False),
        sa.Column('make', sa.String(50), nullable=False),
        sa.Column('model', sa.String(50), nullable=False),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('license_plate', sa.String(20), nullable=False),
        sa.Column('vin', sa.String(17), nullable=True),
        sa.Column('color', sa.String(30), nullable=True),
        sa.Column('fuel_type', sa.String(20), nullable=True),
        sa.UniqueConstraint('tenant_id', 'license_plate', name='uq_vehicle_tenant_plate'),
    )

    op.create_table(
        'job_complaint',
        sa.Column('complaint_id', sa.Integer(), primary_key=True),
        sa.Column('job_id', sa.Integer(), sa.ForeignKey('job.job_id', ondelete='CASCADE'), nullable=False),
        sa.Column('description', sa.String(300), nullable=False),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )

    op.add_column('job', sa.Column('vehicle_id', sa.Integer(), sa.ForeignKey('vehicle.vehicle_id'), nullable=True))
    op.add_column('job', sa.Column('odometer_in', sa.Integer(), nullable=True))
    op.add_column('job', sa.Column('technician_notes', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('job', 'technician_notes')
    op.drop_column('job', 'odometer_in')
    op.drop_column('job', 'vehicle_id')
    op.drop_table('job_complaint')
    op.drop_table('vehicle')
