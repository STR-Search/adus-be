from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from app.core.database import Base


class ClientProfileVersion(Base):
    """What the agent understood about the client, versioned per conversation."""

    __tablename__ = "client_profiles"
    __table_args__ = (
        UniqueConstraint("conversation_id", "version", name="uq_client_profiles_version"),
        Index("ix_client_profiles_conversation_id", "conversation_id"),
        {"schema": "deal_recommendation"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deal_recommendation.conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deal_recommendation.agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    version = Column(Integer, nullable=False)
    profile = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Recommendation(Base):
    """One deal card in a presented shortlist.

    ``underwriting_id`` has no FK: iron_bank is another domain. ``snapshot``
    keeps the numbers the agent saw, at the run's financing terms, so "why did
    it recommend this" stays answerable after analysts edit the underwriting.
    """

    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_run_id", "run_id"),
        Index("ix_recommendations_conversation_id", "conversation_id"),
        {"schema": "deal_recommendation"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deal_recommendation.agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deal_recommendation.conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    rank = Column(Integer, nullable=False)
    underwriting_id = Column(Integer, nullable=False)
    match_score = Column(Numeric(5, 2), nullable=True)
    why = Column(Text, nullable=False)
    matched = Column(ARRAY(Text), nullable=False, server_default="{}")
    missed = Column(ARRAY(Text), nullable=False, server_default="{}")
    snapshot = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
