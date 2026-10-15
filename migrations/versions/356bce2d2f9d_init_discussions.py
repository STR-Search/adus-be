"""init_discussions

Revision ID: 356bce2d2f9d
Revises:
Create Date: 2026-10-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "356bce2d2f9d"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("discussions",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # env.py also creates target schemas on online runs; this keeps offline
    # (--sql) output correct.
    op.execute("CREATE SCHEMA IF NOT EXISTS discussions")


def downgrade() -> None:
    """Downgrade schema."""
    # No CASCADE: fails loudly if any discussions tables still exist.
    op.execute("DROP SCHEMA IF EXISTS discussions")
