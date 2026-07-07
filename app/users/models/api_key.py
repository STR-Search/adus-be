from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)

from app.core.database import Base


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        Index("idx_api_keys_key_hash", "key_hash", unique=True),
        Index("idx_api_keys_user_id", "user_id"),
        {"schema": "users"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(Integer, ForeignKey("users.users.id"), nullable=False)
    name = Column(Text, nullable=False)
    # First 8 chars of the plaintext key, for display/identification only.
    prefix = Column(Text, nullable=False)
    # SHA-256 hex of the full plaintext key. The plaintext is never stored.
    key_hash = Column(Text, nullable=False)

    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
