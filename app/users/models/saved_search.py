from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class SavedSearch(Base):
    """A user's stored filter set for some list endpoint.

    Deliberately generic: ``resource`` namespaces the row to a list view (e.g.
    ``iron_bank.underwritings``) so one table serves every module. Nothing here
    knows what a given resource's filters mean — ``filters`` is opaque JSONB
    that the frontend hands back to repopulate its controls, which is why a new
    module needs a new ``resource`` string and no backend change at all.
    """

    __tablename__ = "saved_searches"
    __table_args__ = (
        # Re-saving under a name the user already used updates that search
        # rather than silently creating a second identical entry in their list.
        UniqueConstraint(
            "user_id", "resource", "name", name="uq_saved_searches_user_resource_name"
        ),
        Index("idx_saved_searches_user_id_resource", "user_id", "resource"),
        {"schema": "users"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(
        Integer,
        ForeignKey("users.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Which list view this search belongs to, e.g. "iron_bank.underwritings".
    resource = Column(Text, nullable=False)
    name = Column(Text, nullable=False)

    filters = Column(JSONB, nullable=False)
    query_string = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
