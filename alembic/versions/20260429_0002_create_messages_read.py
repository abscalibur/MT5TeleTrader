"""create messages_read table

Revision ID: 20260429_0002
Revises: 20260429_0001
Create Date: 2026-04-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260429_0002"
down_revision: Union[str, Sequence[str], None] = "20260429_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "messages_read",
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("message_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_messages_read_channel_id_channels"),
        ),
        sa.PrimaryKeyConstraint("channel_id", "message_id", name=op.f("pk_messages_read")),
    )


def downgrade() -> None:
    op.drop_table("messages_read")
