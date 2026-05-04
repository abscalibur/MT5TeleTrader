"""create interpreted_trades table

Revision ID: 20260429_0004
Revises: 20260429_0003
Create Date: 2026-04-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260429_0004"
down_revision: Union[str, Sequence[str], None] = "20260429_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interpreted_trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("stoploss", sa.Numeric(18, 6), nullable=False),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_interpreted_trades_channel_id_channels"),
        ),
        sa.ForeignKeyConstraint(
            ["channel_id", "message_id"],
            ["messages_read.channel_id", "messages_read.message_id"],
            name=op.f("fk_interpreted_trades_message_read"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interpreted_trades")),
        sa.UniqueConstraint(
            "channel_id",
            "message_id",
            name=op.f("uq_interpreted_trades_channel_id_message_id"),
        ),
    )
    op.create_index(
        op.f("ix_interpreted_trades_channel_id"),
        "interpreted_trades",
        ["channel_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_interpreted_trades_symbol_side"),
        "interpreted_trades",
        ["symbol", "side"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_interpreted_trades_symbol_side"), table_name="interpreted_trades")
    op.drop_index(op.f("ix_interpreted_trades_channel_id"), table_name="interpreted_trades")
    op.drop_table("interpreted_trades")
