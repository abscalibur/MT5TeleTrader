"""add messages_read indexes

Revision ID: 20260429_0003
Revises: 20260429_0002
Create Date: 2026-04-29
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260429_0003"
down_revision: Union[str, Sequence[str], None] = "20260429_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_messages_read_channel_id_message_time"),
        "messages_read",
        ["channel_id", "message_time"],
        unique=False,
    )
    op.create_index(
        op.f("ix_messages_read_processed_message_time"),
        "messages_read",
        ["processed", "message_time"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_messages_read_processed_message_time"), table_name="messages_read")
    op.drop_index(op.f("ix_messages_read_channel_id_message_time"), table_name="messages_read")
