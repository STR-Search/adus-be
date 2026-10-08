"""create_underwriting_threads

Revision ID: a7eb071e1428
Revises: e9b17c4d3a82
Create Date: 2026-10-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7eb071e1428"
down_revision: Union[str, Sequence[str], None] = "e9b17c4d3a82"
branch_labels: Union[str, Sequence[str], None] = None
# discussions.threads must exist for the thread_id FK.
depends_on: Union[str, Sequence[str], None] = ("26237c59cd08",)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "underwriting_threads",
        sa.Column("underwriting_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind", sa.Text(), server_default=sa.text("'general'"), nullable=False
        ),
        sa.Column("thread_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("underwriting_id", "kind"),
        # Deleting an underwriting removes only this link; the thread is kept.
        sa.ForeignKeyConstraint(
            ["underwriting_id"], ["iron_bank.underwritings.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["discussions.threads.id"], ondelete="CASCADE"
        ),
        # One underwriting version per thread.
        sa.UniqueConstraint("thread_id", name="uq_underwriting_threads_thread"),
        schema="iron_bank",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("underwriting_threads", schema="iron_bank")
