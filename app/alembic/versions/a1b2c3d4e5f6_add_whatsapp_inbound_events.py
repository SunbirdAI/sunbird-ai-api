"""add_whatsapp_inbound_events

Additive, non-destructive migration: creates the whatsapp_inbound_events table
used for cross-instance inbound message deduplication (Phase 3A). No changes to
existing tables.

Revision ID: a1b2c3d4e5f6
Revises: 5c35ed08c5d4
Create Date: 2026-07-02 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "5c35ed08c5d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_inbound_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="processing",
        ),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_whatsapp_inbound_events_id"),
        "whatsapp_inbound_events",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whatsapp_inbound_events_message_id"),
        "whatsapp_inbound_events",
        ["message_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_whatsapp_inbound_events_user_id"),
        "whatsapp_inbound_events",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_whatsapp_inbound_events_user_id"),
        table_name="whatsapp_inbound_events",
    )
    op.drop_index(
        op.f("ix_whatsapp_inbound_events_message_id"),
        table_name="whatsapp_inbound_events",
    )
    op.drop_index(
        op.f("ix_whatsapp_inbound_events_id"),
        table_name="whatsapp_inbound_events",
    )
    op.drop_table("whatsapp_inbound_events")
