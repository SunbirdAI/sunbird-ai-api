"""add_whatsapp_persistence_tables

Revision ID: 4a9f7b2c1d33
Revises: e316767611c2
Create Date: 2026-02-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4a9f7b2c1d33"
down_revision = "e316767611c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_user_preferences",
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("source_language", sa.String(length=64), nullable=False),
        sa.Column("target_language", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
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
        op.f("ix_whatsapp_user_preferences_user_id"),
        "whatsapp_user_preferences",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=True),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_whatsapp_messages_id"), "whatsapp_messages", ["id"], unique=False)
    op.create_index(
        op.f("ix_whatsapp_messages_message_id"),
        "whatsapp_messages",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whatsapp_messages_message_type"),
        "whatsapp_messages",
        ["message_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whatsapp_messages_user_id"),
        "whatsapp_messages",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "whatsapp_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=True),
        sa.Column("sender_name", sa.String(length=255), nullable=True),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("bot_response", sa.Text(), nullable=False),
        sa.Column("feedback", sa.String(length=64), nullable=False),
        sa.Column("feedback_type", sa.String(length=32), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_whatsapp_feedback_id"), "whatsapp_feedback", ["id"], unique=False)
    op.create_index(
        op.f("ix_whatsapp_feedback_message_id"),
        "whatsapp_feedback",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whatsapp_feedback_user_id"),
        "whatsapp_feedback",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_whatsapp_feedback_user_id"), table_name="whatsapp_feedback")
    op.drop_index(op.f("ix_whatsapp_feedback_message_id"), table_name="whatsapp_feedback")
    op.drop_index(op.f("ix_whatsapp_feedback_id"), table_name="whatsapp_feedback")
    op.drop_table("whatsapp_feedback")

    op.drop_index(op.f("ix_whatsapp_messages_user_id"), table_name="whatsapp_messages")
    op.drop_index(op.f("ix_whatsapp_messages_message_type"), table_name="whatsapp_messages")
    op.drop_index(op.f("ix_whatsapp_messages_message_id"), table_name="whatsapp_messages")
    op.drop_index(op.f("ix_whatsapp_messages_id"), table_name="whatsapp_messages")
    op.drop_table("whatsapp_messages")

    op.drop_index(
        op.f("ix_whatsapp_user_preferences_user_id"),
        table_name="whatsapp_user_preferences",
    )
    op.drop_table("whatsapp_user_preferences")
