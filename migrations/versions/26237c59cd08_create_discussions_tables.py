"""create_discussions_tables

Revision ID: 26237c59cd08
Revises: 356bce2d2f9d
Create Date: 2026-10-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "26237c59cd08"
down_revision: Union[str, Sequence[str], None] = "356bce2d2f9d"
branch_labels: Union[str, Sequence[str], None] = None
# users.users must exist for the author / creator / mention FKs.
depends_on: Union[str, Sequence[str], None] = ("b7e9a21cb997",)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "threads",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(always=True), nullable=False
        ),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "comment_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        # FK to comments is added below, after comments exists.
        sa.Column("last_comment_id", sa.BigInteger(), nullable=True),
        sa.Column("last_comment_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.users.id"], ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "comment_count >= 0", name="ck_threads_comment_count_nonneg"
        ),
        schema="discussions",
    )

    op.create_table(
        "comments",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(always=True), nullable=False
        ),
        sa.Column("thread_id", sa.BigInteger(), nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=False),
        sa.Column("parent_comment_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "body_version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["discussions.threads.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"], ["users.users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("thread_id", "id", name="uq_comments_thread_id_id"),
        sa.CheckConstraint(
            "parent_comment_id IS NULL OR parent_comment_id <> id",
            name="ck_comments_parent_not_self",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(body) = 'object'", name="ck_comments_body_object"
        ),
        sa.CheckConstraint("body_version >= 1", name="ck_comments_body_version"),
        schema="discussions",
    )

    # Replies stay in their parent's thread. Added after the table so the
    # (thread_id, id) unique constraint it targets already exists. Default
    # NO ACTION (not RESTRICT) lets a thread delete cascade through all of its
    # comments in a single statement.
    op.create_foreign_key(
        "fk_comments_parent_same_thread",
        "comments",
        "comments",
        ["thread_id", "parent_comment_id"],
        ["thread_id", "id"],
        source_schema="discussions",
        referent_schema="discussions",
    )

    op.create_index(
        "idx_comments_thread_timeline",
        "comments",
        ["thread_id", "created_at", "id"],
        unique=False,
        schema="discussions",
    )
    op.create_index(
        "idx_comments_author",
        "comments",
        ["author_user_id"],
        unique=False,
        schema="discussions",
    )

    # Circular reference: a thread points at its latest comment.
    op.create_foreign_key(
        "fk_threads_last_comment",
        "threads",
        "comments",
        ["last_comment_id"],
        ["id"],
        source_schema="discussions",
        referent_schema="discussions",
        ondelete="SET NULL",
    )

    op.create_table(
        "comment_mentions",
        sa.Column("comment_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("comment_id", "user_id"),
        sa.ForeignKeyConstraint(
            ["comment_id"], ["discussions.comments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.users.id"], ondelete="CASCADE"),
        schema="discussions",
    )
    op.create_index(
        "idx_comment_mentions_user",
        "comment_mentions",
        ["user_id", "comment_id"],
        unique=False,
        schema="discussions",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "idx_comment_mentions_user", table_name="comment_mentions", schema="discussions"
    )
    op.drop_table("comment_mentions", schema="discussions")

    op.drop_constraint(
        "fk_threads_last_comment", "threads", type_="foreignkey", schema="discussions"
    )

    op.drop_index("idx_comments_author", table_name="comments", schema="discussions")
    op.drop_index(
        "idx_comments_thread_timeline", table_name="comments", schema="discussions"
    )
    op.drop_constraint(
        "fk_comments_parent_same_thread",
        "comments",
        type_="foreignkey",
        schema="discussions",
    )
    op.drop_table("comments", schema="discussions")
    op.drop_table("threads", schema="discussions")
