"""init_deal_recommendation

Revision ID: 92e6e6fe4b8e
Revises:
Create Date: 2026-10-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "92e6e6fe4b8e"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("deal_recommendation",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # env.py also creates target schemas on online runs; this keeps offline
    # (--sql) output correct.
    op.execute("CREATE SCHEMA IF NOT EXISTS deal_recommendation")


def downgrade() -> None:
    """Downgrade schema."""
    # No CASCADE: fails loudly if any deal_recommendation tables still exist.
    op.execute("DROP SCHEMA IF EXISTS deal_recommendation")
