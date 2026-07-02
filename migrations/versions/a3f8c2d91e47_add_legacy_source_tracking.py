"""add_legacy_source_tracking

Adds provenance for the legacy Google Sheet backfill:
- underwritings.source ('adus' | 'legacy_sheet')
- underwritings.sheet_number (the deal's tab/link number in the sheet),
  partial-unique so re-running the backfill can never duplicate a deal
- widens deal_status to 100 chars and extends its CHECK so legacy rows can
  hold a dynamic "Previously Underwritten - <sheet status>" string alongside
  the fixed enum keys. A CHECK's expression cannot be modified once created,
  so each direction drops the constraint and recreates its own version.

Revision ID: a3f8c2d91e47
Revises: 5b1e7a4c3d2f
Create Date: 2026-07-02 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f8c2d91e47"
down_revision: Union[str, Sequence[str], None] = "5b1e7a4c3d2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Current constraint (pre-migration), restored on downgrade.
OLD_DEAL_STATUS_CHECK = (
    "deal_status IS NULL OR deal_status IN ("
    "'template_generated', "
    "'analyst_started', "
    "'analyst_completed', "
    "'delete_zillow', "
    "'delete_deal', "
    "'maybe', "
    "'re_forecast_revenue', "
    "'awaiting_realtor_details', "
    "'present_to_clients', "
    "'client_under_contract', "
    "'training_deal'"
    ")"
)

# Same enum keys, plus the dynamic legacy-status pattern, applied on upgrade.
NEW_DEAL_STATUS_CHECK = (
    OLD_DEAL_STATUS_CHECK + " OR deal_status LIKE 'Previously Underwritten - %'"
)


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
    op.alter_column(
        "underwritings",
        "deal_status",
        type_=sa.String(100),
        existing_type=sa.String(50),
        schema="iron_bank",
    )
    op.drop_constraint(
        "ck_underwritings_deal_status",
        "underwritings",
        schema="iron_bank",
        type_="check",
    )
    op.create_check_constraint(
        "ck_underwritings_deal_status",
        "underwritings",
        NEW_DEAL_STATUS_CHECK,
        schema="iron_bank",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_underwritings_deal_status",
        "underwritings",
        schema="iron_bank",
        type_="check",
    )
    op.create_check_constraint(
        "ck_underwritings_deal_status",
        "underwritings",
        OLD_DEAL_STATUS_CHECK,
        schema="iron_bank",
    )
    op.alter_column(
        "underwritings",
        "deal_status",
        type_=sa.String(50),
        existing_type=sa.String(100),
        schema="iron_bank",
    )
    op.drop_index(
        "uq_underwritings_sheet_number",
        "underwritings",
        schema="iron_bank",
    )
    op.drop_column("underwritings", "sheet_number", schema="iron_bank")
    op.drop_column("underwritings", "source", schema="iron_bank")
