from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

# Registers discussions.threads in the shared metadata so the string FK below
# resolves. Importing from app/core is allowed; no domain model is imported.
import app.core.discussions.models  # noqa: F401
from app.core.database import Base


class UnderwritingThread(Base):
    """Links an underwriting to its discussion thread(s), one per ``kind``.

    iron_bank owns this link so ``discussions.threads`` never references a
    domain table. Deleting an underwriting removes only the link; the thread
    and its comments are kept. ``thread_id`` is unique, so a thread belongs to
    exactly one underwriting version.
    """

    __tablename__ = "underwriting_threads"
    __table_args__ = (
        UniqueConstraint("thread_id", name="uq_underwriting_threads_thread"),
        {"schema": "iron_bank"},
    )

    underwriting_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("iron_bank.underwritings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    kind: Mapped[str] = mapped_column(
        Text, primary_key=True, default="general", server_default=text("'general'")
    )
    thread_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("discussions.threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
