"""add trade uuid to interpreted trades

Revision ID: 20260429_0006
Revises: 20260429_0005
Create Date: 2026-04-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260429_0006"
down_revision: Union[str, Sequence[str], None] = "20260429_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("interpreted_trades", schema=None) as batch_op:
        batch_op.add_column(sa.Column("trade_uuid", sa.String(length=36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("interpreted_trades", schema=None) as batch_op:
        batch_op.drop_column("trade_uuid")
