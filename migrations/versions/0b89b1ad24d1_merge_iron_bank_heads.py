"""merge iron_bank heads

Revision ID: 0b89b1ad24d1
Revises: a3f8c2d91e47, d3f8a1c9b204
Create Date: 2026-07-29 21:08:37.675668

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b89b1ad24d1'
down_revision: Union[str, Sequence[str], None] = ('a3f8c2d91e47', 'd3f8a1c9b204')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
