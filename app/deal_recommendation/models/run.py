import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class AgentRun(Base):
    """One agent run: everything the agent did in response to one user message."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'capped')",
            name="ck_agent_runs_status",
        ),
        Index("ix_agent_runs_conversation_id", "conversation_id"),
        {"schema": "deal_recommendation"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deal_recommendation.conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_message_id = Column(
        BigInteger,
        ForeignKey("deal_recommendation.messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    model = Column(Text, nullable=False)
    effort = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="running", server_default="running")
    stop_reason = Column(Text, nullable=True)
    iterations = Column(Integer, nullable=False, default=0, server_default="0")
    input_tokens = Column(Integer, nullable=False, default=0, server_default="0")
    output_tokens = Column(Integer, nullable=False, default=0, server_default="0")
    cache_read_tokens = Column(Integer, nullable=False, default=0, server_default="0")
    cache_write_tokens = Column(Integer, nullable=False, default=0, server_default="0")
    cost_usd = Column(Numeric(10, 4), nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class ToolCall(Base):
    """One tool call inside a run — the trace of what the agent looked at."""

    __tablename__ = "tool_calls"
    __table_args__ = (
        Index("ix_tool_calls_run_id", "run_id"),
        {"schema": "deal_recommendation"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deal_recommendation.agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq = Column(Integer, nullable=False)
    tool_use_id = Column(Text, nullable=True)
    tool_name = Column(Text, nullable=False)
    input = Column(JSONB, nullable=False)
    output = Column(JSONB, nullable=False)
    is_error = Column(Boolean, nullable=False, default=False, server_default="false")
    duration_ms = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
