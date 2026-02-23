"""default_whatsapp_tts_off

Revision ID: d8e3b4a9f2c1
Revises: c6f77d2e81ab
Create Date: 2026-02-23 00:00:02.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d8e3b4a9f2c1"
down_revision = "c6f77d2e81ab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "whatsapp_user_preferences",
        "tts_enabled",
        server_default=sa.text("false"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "whatsapp_user_preferences",
        "tts_enabled",
        server_default=sa.text("true"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
