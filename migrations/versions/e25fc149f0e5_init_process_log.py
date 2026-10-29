"""init_process_log

Revision ID: e25fc149f0e5
Revises:
Create Date: 2026-10-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e25fc149f0e5"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("process_log",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # env.py also creates target schemas on online runs; this keeps offline
    # (--sql) output correct.
    op.execute("CREATE SCHEMA IF NOT EXISTS process_log")


def downgrade() -> None:
    """Downgrade schema."""
    # No CASCADE: fails loudly if any process_log tables still exist.
    op.execute("DROP SCHEMA IF EXISTS process_log")
