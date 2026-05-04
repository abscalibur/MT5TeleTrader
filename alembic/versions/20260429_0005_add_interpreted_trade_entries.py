"""add interpreted trade entries

Revision ID: 20260429_0005
Revises: 20260429_0004
Create Date: 2026-04-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260429_0005"
down_revision: Union[str, Sequence[str], None] = "20260429_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("interpreted_trades", schema=None) as batch_op:
        batch_op.add_column(sa.Column("entryprice", sa.Numeric(18, 6), nullable=True))
        batch_op.drop_constraint(
            "uq_interpreted_trades_channel_id_message_id",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_interpreted_trades_channel_id_message_id_entryprice",
            ["channel_id", "message_id", "entryprice"],
        )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM interpreted_trades
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM interpreted_trades
            GROUP BY channel_id, message_id
        )
        """
    )
    with op.batch_alter_table("interpreted_trades", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_interpreted_trades_channel_id_message_id_entryprice",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_interpreted_trades_channel_id_message_id",
            ["channel_id", "message_id"],
        )
        batch_op.drop_column("entryprice")
