"""create_deal_recommendation_tables

Revision ID: 1e5d030555a3
Revises: 92e6e6fe4b8e
Create Date: 2026-10-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "1e5d030555a3"
down_revision: Union[str, Sequence[str], None] = "92e6e6fe4b8e"
branch_labels: Union[str, Sequence[str], None] = None
# users.users must exist for conversations.created_by_user_id.
depends_on: Union[str, Sequence[str], None] = ("b7e9a21cb997",)

SCHEMA = "deal_recommendation"


def _timestamp(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=nullable,
    )


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "status IN ('active', 'archived')", name="ck_conversations_status"
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        _timestamp("created_at"),
        sa.UniqueConstraint("conversation_id", "seq", name="uq_messages_conversation_seq"),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')", name="ck_messages_role"
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_message_id",
            sa.BigInteger(),
            sa.ForeignKey(f"{SCHEMA}.messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("effort", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="running", nullable=False),
        sa.Column("stop_reason", sa.Text(), nullable=True),
        sa.Column("iterations", sa.Integer(), server_default="0", nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        _timestamp("started_at"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'capped')",
            name="ck_agent_runs_status",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_agent_runs_conversation_id", "agent_runs", ["conversation_id"], schema=SCHEMA
    )
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("tool_use_id", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("input", postgresql.JSONB(), nullable=False),
        sa.Column("output", postgresql.JSONB(), nullable=False),
        sa.Column("is_error", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("duration_ms", sa.Integer(), server_default="0", nullable=False),
        _timestamp("created_at"),
        schema=SCHEMA,
    )
    op.create_index("ix_tool_calls_run_id", "tool_calls", ["run_id"], schema=SCHEMA)
    op.create_table(
        "client_profiles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.agent_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("profile", postgresql.JSONB(), nullable=False),
        _timestamp("created_at"),
        sa.UniqueConstraint("conversation_id", "version", name="uq_client_profiles_version"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_client_profiles_conversation_id",
        "client_profiles",
        ["conversation_id"],
        schema=SCHEMA,
    )
    op.create_table(
        "recommendations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        # No FK: iron_bank is another domain.
        sa.Column("underwriting_id", sa.Integer(), nullable=False),
        sa.Column("match_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("why", sa.Text(), nullable=False),
        sa.Column("matched", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("missed", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        _timestamp("created_at"),
        schema=SCHEMA,
    )
    op.create_index("ix_recommendations_run_id", "recommendations", ["run_id"], schema=SCHEMA)
    op.create_index(
        "ix_recommendations_conversation_id",
        "recommendations",
        ["conversation_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("recommendations", schema=SCHEMA)
    op.drop_table("client_profiles", schema=SCHEMA)
    op.drop_table("tool_calls", schema=SCHEMA)
    op.drop_table("agent_runs", schema=SCHEMA)
    op.drop_table("messages", schema=SCHEMA)
    op.drop_table("conversations", schema=SCHEMA)
