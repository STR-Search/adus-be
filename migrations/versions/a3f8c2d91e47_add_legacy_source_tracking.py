"""add_legacy_source_tracking

Adds provenance for the legacy Google Sheet backfill:
- underwritings.source ('adus' | 'legacy_sheet')
- underwritings.sheet_number (the deal's tab/link number in the sheet),
  partial-unique so re-running the backfill can never duplicate a deal

Revision ID: a3f8c2d91e47
Revises: 5b1e7a4c3d2f
Create Date: 2026-07-02 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f8c2d91e47"
down_revision: Union[str, Sequence[str], None] = "d3f8a1c9b204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "underwritings",
        sa.Column("source", sa.String(50), nullable=True, server_default="adus"),
        schema="iron_bank",
    )
    op.add_column(
        "underwritings",
        sa.Column("sheet_number", sa.Integer(), nullable=True),
        schema="iron_bank",
    )
    op.create_index(
        "uq_underwritings_sheet_number",
        "underwritings",
        ["sheet_number"],
        unique=True,
        schema="iron_bank",
        postgresql_where=sa.text("sheet_number IS NOT NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_underwritings_sheet_number",
        "underwritings",
        schema="iron_bank",
    )
    op.drop_column("underwritings", "sheet_number", schema="iron_bank")
    op.drop_column("underwritings", "source", schema="iron_bank")
