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


class Snapshot(Base):
    """The subject's state after a transition, built by the owning domain.

    Deduplicated per subject by ``payload_hash``: consecutive transitions that
    leave the subject's data unchanged share one row.
    """

    __tablename__ = "snapshots"
    __table_args__ = (
        UniqueConstraint(
            "subject_type",
            "subject_id",
            "payload_hash",
            name="uq_snapshots_subject_hash",
        ),
        CheckConstraint("schema_version >= 1", name="ck_snapshots_schema_version"),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object'", name="ck_snapshots_payload_object"
        ),
        {"schema": "process_log"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Transition(Base):
    """One status change of a subject's flow, linked to the one before it.

    Each ``(subject_type, subject_id, flow)`` is a singly linked list: the head
    has no ``previous_transition_id`` and no ``from_status``; every other row
    follows exactly one row of the same subject and flow, and its
    ``from_status`` equals that row's ``to_status`` (composite self-FK). No
    row has two successors, so the chain cannot fork.

    A successor is always inserted after its predecessor exists, so ``id``
    order within a chain is chain order. ``occurred_at`` is informational and
    may disagree (backfilled rows set it explicitly).
    """

    __tablename__ = "transitions"
    __table_args__ = (
        UniqueConstraint("previous_transition_id", name="uq_transitions_previous"),
        UniqueConstraint(
            "id",
            "subject_type",
            "subject_id",
            "flow",
            "to_status",
            name="uq_transitions_link_target",
        ),
        ForeignKeyConstraint(
            [
                "previous_transition_id",
                "subject_type",
                "subject_id",
                "flow",
                "from_status",
            ],
            [
                "process_log.transitions.id",
                "process_log.transitions.subject_type",
                "process_log.transitions.subject_id",
                "process_log.transitions.flow",
                "process_log.transitions.to_status",
            ],
            name="fk_transitions_previous",
        ),
        CheckConstraint(
            "(previous_transition_id IS NULL) = (from_status IS NULL)",
            name="ck_transitions_head_has_no_from",
        ),
        CheckConstraint(
            "from_status IS DISTINCT FROM to_status",
            name="ck_transitions_changes_status",
        ),
        CheckConstraint(
            "source IN ('api', 'job', 'backfill', 'system')",
            name="ck_transitions_source",
        ),
        Index(
            "uq_transitions_head",
            "subject_type",
            "subject_id",
            "flow",
            unique=True,
            postgresql_where=text("previous_transition_id IS NULL"),
        ),
        Index("idx_transitions_chain", "subject_type", "subject_id", "flow", "id"),
        Index("idx_transitions_flow_status", "flow", "to_status", "occurred_at"),
        Index(
            "idx_transitions_actor",
            "actor_user_id",
            postgresql_where=text("actor_user_id IS NOT NULL"),
        ),
        Index(
            "idx_transitions_snapshot",
            "snapshot_id",
            postgresql_where=text("snapshot_id IS NOT NULL"),
        ),
        {"schema": "process_log"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    flow: Mapped[str] = mapped_column(Text, nullable=False)
    previous_transition_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    from_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ``metadata`` is reserved on declarative classes; the column keeps the name.
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    snapshot_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("process_log.snapshots.id", ondelete="RESTRICT"),
        nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
