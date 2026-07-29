import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class Job(Base):
    """Durable record of an async batch job. Source of truth for status/result."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_jobs_status",
        ),
        {"schema": "iron_bank"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_type = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="queued", server_default="queued")
    params = Column(JSONB, nullable=False)
    result = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
