import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class Conversation(Base):
    """One chat thread: a team member working one client's recommendations."""

    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')", name="ck_conversations_status"
        ),
        {"schema": "deal_recommendation"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(Text, nullable=True)
    created_by_user_id = Column(
        Integer, ForeignKey("users.users.id", ondelete="SET NULL"), nullable=True
    )
    model = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="active", server_default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Message(Base):
    """The exact Claude message history, append-only.

    ``content`` is stored exactly as sent to / received from Claude (thinking,
    tool_use and tool_result blocks included) and never rewritten: continuing a
    conversation replays these rows in ``seq`` order.
    """

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_messages_conversation_seq"),
        CheckConstraint(
            "role IN ('user', 'assistant')", name="ck_messages_role"
        ),
        {"schema": "deal_recommendation"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deal_recommendation.conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq = Column(Integer, nullable=False)
    role = Column(Text, nullable=False)
    content = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
