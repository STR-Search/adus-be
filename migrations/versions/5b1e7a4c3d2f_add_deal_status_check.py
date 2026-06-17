"""add_deal_status_check

Revision ID: 5b1e7a4c3d2f
Revises: 17135fae4036
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b1e7a4c3d2f"
down_revision: Union[str, Sequence[str], None] = "17135fae4036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEAL_STATUS_CHECK = (
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


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "ck_underwritings_deal_status",
        "underwritings",
        DEAL_STATUS_CHECK,
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
