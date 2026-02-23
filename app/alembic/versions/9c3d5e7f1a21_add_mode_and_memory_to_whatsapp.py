"""add_mode_and_memory_to_whatsapp

Revision ID: 9c3d5e7f1a21
Revises: 4a9f7b2c1d33
Create Date: 2026-02-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9c3d5e7f1a21"
down_revision = "4a9f7b2c1d33"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_user_preferences",
        sa.Column(
            "mode",
            sa.String(length=16),
            nullable=False,
            server_default="chat",
        ),
    )

    op.create_table(
        "whatsapp_user_memory",
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("memory_note", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "last_summarized_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_whatsapp_user_memory_user_id"),
        "whatsapp_user_memory",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_whatsapp_user_memory_user_id"), table_name="whatsapp_user_memory")
    op.drop_table("whatsapp_user_memory")
    op.drop_column("whatsapp_user_preferences", "mode")
