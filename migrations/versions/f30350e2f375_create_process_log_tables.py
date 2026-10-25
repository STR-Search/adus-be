"""create_process_log_tables

Revision ID: f30350e2f375
Revises: e25fc149f0e5
Create Date: 2026-10-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f30350e2f375"
down_revision: Union[str, Sequence[str], None] = "e25fc149f0e5"
branch_labels: Union[str, Sequence[str], None] = None
# users.users must exist for the actor FK.
depends_on: Union[str, Sequence[str], None] = ("b7e9a21cb997",)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "snapshots",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(always=True), nullable=False
        ),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.BigInteger(), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subject_type",
            "subject_id",
            "payload_hash",
            name="uq_snapshots_subject_hash",
        ),
        sa.CheckConstraint(
            "schema_version >= 1", name="ck_snapshots_schema_version"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'", name="ck_snapshots_payload_object"
        ),
        schema="process_log",
    )

    op.create_table(
        "transitions",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(always=True), nullable=False
        ),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.BigInteger(), nullable=False),
        sa.Column("flow", sa.Text(), nullable=False),
        sa.Column("previous_transition_id", sa.BigInteger(), nullable=True),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["process_log.snapshots.id"], ondelete="RESTRICT"
        ),
        # One successor per row: the chain cannot fork.
        sa.UniqueConstraint(
            "previous_transition_id", name="uq_transitions_previous"
        ),
        # Target of the composite self-FK below.
        sa.UniqueConstraint(
            "id",
            "subject_type",
            "subject_id",
            "flow",
            "to_status",
            name="uq_transitions_link_target",
        ),
        sa.CheckConstraint(
            "(previous_transition_id IS NULL) = (from_status IS NULL)",
            name="ck_transitions_head_has_no_from",
        ),
        sa.CheckConstraint(
            "from_status IS DISTINCT FROM to_status",
            name="ck_transitions_changes_status",
        ),
        sa.CheckConstraint(
            "source IN ('api', 'job', 'backfill', 'system')",
            name="ck_transitions_source",
        ),
        schema="process_log",
    )

    # A row may only follow a row of the same subject and flow, and its
    # from_status must equal that row's to_status. Added after the table so the
    # unique constraint it targets already exists. MATCH SIMPLE (the default)
    # skips head rows, whose previous_transition_id and from_status are NULL.
    # Default NO ACTION (not RESTRICT): a row with a successor still can't be
    # deleted alone, but a whole chain can be deleted in one statement.
    op.create_foreign_key(
        "fk_transitions_previous",
        "transitions",
        "transitions",
        [
            "previous_transition_id",
            "subject_type",
            "subject_id",
            "flow",
            "from_status",
        ],
        ["id", "subject_type", "subject_id", "flow", "to_status"],
        source_schema="process_log",
        referent_schema="process_log",
    )

    # One head per (subject, flow).
    op.create_index(
        "uq_transitions_head",
        "transitions",
        ["subject_type", "subject_id", "flow"],
        unique=True,
        schema="process_log",
        postgresql_where=sa.text("previous_transition_id IS NULL"),
    )
    op.create_index(
        "idx_transitions_chain",
        "transitions",
        ["subject_type", "subject_id", "flow", "id"],
        unique=False,
        schema="process_log",
    )
    op.create_index(
        "idx_transitions_flow_status",
        "transitions",
        ["flow", "to_status", "occurred_at"],
        unique=False,
        schema="process_log",
    )
    op.create_index(
        "idx_transitions_actor",
        "transitions",
        ["actor_user_id"],
        unique=False,
        schema="process_log",
        postgresql_where=sa.text("actor_user_id IS NOT NULL"),
    )
    op.create_index(
        "idx_transitions_snapshot",
        "transitions",
        ["snapshot_id"],
        unique=False,
        schema="process_log",
        postgresql_where=sa.text("snapshot_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "idx_transitions_snapshot", table_name="transitions", schema="process_log"
    )
    op.drop_index(
        "idx_transitions_actor", table_name="transitions", schema="process_log"
    )
    op.drop_index(
        "idx_transitions_flow_status", table_name="transitions", schema="process_log"
    )
    op.drop_index(
        "idx_transitions_chain", table_name="transitions", schema="process_log"
    )
    op.drop_index(
        "uq_transitions_head", table_name="transitions", schema="process_log"
    )
    op.drop_constraint(
        "fk_transitions_previous",
        "transitions",
        type_="foreignkey",
        schema="process_log",
    )
    op.drop_table("transitions", schema="process_log")
    op.drop_table("snapshots", schema="process_log")
