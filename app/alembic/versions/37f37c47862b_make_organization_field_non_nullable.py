"""Make organization field non-nullable

Revision ID: 37f37c47862b
Revises: 96762ef5fd5e
Create Date: 2023-05-22 08:50:52.487458

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '37f37c47862b'
down_revision = '96762ef5fd5e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.execute("UPDATE users SET organization = 'UNKNOWN'")
    op.alter_column('users', 'organization',
               existing_type=sa.VARCHAR(),
               nullable=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('users', 'organization',
               existing_type=sa.VARCHAR(),
               nullable=True)
    # ### end Alembic commands ###
