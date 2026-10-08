from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Thread(Base):
    """A conversation about one subject (e.g. an underwriting).

    The subject is not referenced here: each domain owns a link table pointing
    at ``threads.id``. ``subject_type`` records which domain owns the link and
    never changes after creation. The counters are maintained by the comment
    service in the same transaction as each comment write.
    """

    __tablename__ = "threads"
    __table_args__ = (
        CheckConstraint("comment_count >= 0", name="ck_threads_comment_count_nonneg"),
        {"schema": "discussions"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    comment_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # Circular with comments.thread_id; created after comments in the migration.
    last_comment_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "discussions.comments.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_threads_last_comment",
        ),
        nullable=True,
    )
    last_comment_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Comment(Base):
    """A single message in a thread.

    ``body`` is a normalized Tiptap/ProseMirror document whose format is
    identified by ``body_version``. ``body_text`` is derived from it by the
    server. ``parent_comment_id`` is reserved for replies; the composite FK
    keeps a reply in the same thread as its parent.
    """

    __tablename__ = "comments"
    __table_args__ = (
        UniqueConstraint("thread_id", "id", name="uq_comments_thread_id_id"),
        ForeignKeyConstraint(
            ["thread_id", "parent_comment_id"],
            ["discussions.comments.thread_id", "discussions.comments.id"],
            name="fk_comments_parent_same_thread",
        ),
        CheckConstraint(
            "parent_comment_id IS NULL OR parent_comment_id <> id",
            name="ck_comments_parent_not_self",
        ),
        CheckConstraint(
            "jsonb_typeof(body) = 'object'", name="ck_comments_body_object"
        ),
        CheckConstraint("body_version >= 1", name="ck_comments_body_version"),
        Index("idx_comments_thread_timeline", "thread_id", "created_at", "id"),
        Index("idx_comments_author", "author_user_id"),
        {"schema": "discussions"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    thread_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("discussions.threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    parent_comment_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    body_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default=text("1")
    )
    body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CommentMention(Base):
    """One row per distinct user mentioned in a comment, derived from its body."""

    __tablename__ = "comment_mentions"
    __table_args__ = (
        Index("idx_comment_mentions_user", "user_id", "comment_id"),
        {"schema": "discussions"},
    )

    comment_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("discussions.comments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
