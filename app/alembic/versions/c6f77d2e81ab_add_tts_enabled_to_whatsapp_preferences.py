"""add_tts_enabled_to_whatsapp_preferences

Revision ID: c6f77d2e81ab
Revises: 9c3d5e7f1a21
Create Date: 2026-02-23 00:00:01.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c6f77d2e81ab"
down_revision = "9c3d5e7f1a21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_user_preferences",
        sa.Column(
            "tts_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("whatsapp_user_preferences", "tts_enabled")
