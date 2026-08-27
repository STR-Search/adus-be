"""add_underwriting_versioning

Adds lineage columns so an underwriting can be duplicated into a new version:
- underwritings.series_id — identifies the family of versions
- underwritings.version — 0..N within a series
- underwritings.copied_from_id — the exact row this one was duplicated from

series_id is a UUID rather than a self-referencing "root id" on purpose: it needs
no insert-then-update dance to point a new original at itself, and it survives
deletion of any member (deals do get pruned via delete_deal / delete_zillow), so
the surviving versions keep their family and each other.

Revision ID: e9b17c4d3a82
Revises: a3f8c2d91e47
Create Date: 2026-08-25 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e9b17c4d3a82"
down_revision: Union[str, Sequence[str], None] = "a3f8c2d91e47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Added nullable, then backfilled per row, then set NOT NULL. A column
    # DEFAULT alone would not do: every existing underwriting is its own
    # one-member family and needs a *distinct* series_id, so the UPDATE has to
    # run before the default is attached (the default is for future inserts).
    op.add_column(
        "underwritings",
        sa.Column("series_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="iron_bank",
    )
    op.execute(
        "UPDATE iron_bank.underwritings SET series_id = gen_random_uuid()"
    )
    op.alter_column(
        "underwritings",
        "series_id",
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
        schema="iron_bank",
    )

    # Existing rows are all originals, so the 0 default backfills them correctly.
    op.add_column(
        "underwritings",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="iron_bank",
    )
    op.add_column(
        "underwritings",
        sa.Column("copied_from_id", sa.Integer(), nullable=True),
        schema="iron_bank",
    )
    # SET NULL, not CASCADE: deleting the row a copy was made from must blur the
    # chain, never delete the copy.
    op.create_foreign_key(
        "fk_underwritings_copied_from_id",
        "underwritings",
        "underwritings",
        ["copied_from_id"],
        ["id"],
        source_schema="iron_bank",
        referent_schema="iron_bank",
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_underwritings_copied_from_id",
        "underwritings",
        ["copied_from_id"],
        schema="iron_bank",
    )

    # Version numbers are assigned with max(version) + 1, which races under
    # concurrent duplicates. This constraint turns that race into a retryable
    # IntegrityError instead of two rows silently sharing a version, and its
    # btree also serves the "other versions of this deal" lookup.
    op.create_unique_constraint(
        "uq_underwritings_series_version",
        "underwritings",
        ["series_id", "version"],
        schema="iron_bank",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_underwritings_series_version",
        "underwritings",
        schema="iron_bank",
        type_="unique",
    )
    op.drop_index(
        "ix_underwritings_copied_from_id",
        "underwritings",
        schema="iron_bank",
    )
    op.drop_constraint(
        "fk_underwritings_copied_from_id",
        "underwritings",
        schema="iron_bank",
        type_="foreignkey",
    )
    op.drop_column("underwritings", "copied_from_id", schema="iron_bank")
    op.drop_column("underwritings", "version", schema="iron_bank")
    op.drop_column("underwritings", "series_id", schema="iron_bank")
