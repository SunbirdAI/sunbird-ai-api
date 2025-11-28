"""add_status_code_to_endpoint_logs

Revision ID: e316767611c2
Revises: 95cf3c1435d0
Create Date: 2025-11-27 15:56:58.431749

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e316767611c2'
down_revision = '95cf3c1435d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add status_code column to endpoint_logs table with default value of 200
    op.add_column('endpoint_logs', sa.Column('status_code', sa.Integer(), server_default='200', nullable=True))


def downgrade() -> None:
    # Remove status_code column from endpoint_logs table
    op.drop_column('endpoint_logs', 'status_code')
