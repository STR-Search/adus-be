from sqlalchemy import Boolean, Column, DateTime, Index, Integer, Text, func

from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("idx_users_clerk_id", "clerk_id"),
        {"schema": "users"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    clerk_id = Column(Text, nullable=False, unique=True)
    email = Column(Text, nullable=True)
    first_name = Column(Text, nullable=True)
    last_name = Column(Text, nullable=True)

    is_deleted = Column(Boolean, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # updated_at is maintained by the `users_updated_at` DB trigger (see migration),
    # not by the ORM.
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
