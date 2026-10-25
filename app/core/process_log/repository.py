"""Data access for ``process_log`` tables.

Never commits: it only executes and flushes. The caller owns the transaction,
because a transition must land atomically with the status change it records.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.process_log.exceptions import ConcurrentTransitionError
from app.core.process_log.models import Snapshot, Transition

# Unique constraints an insert hits when another transaction extended the
# chain first. Any other IntegrityError is a bug and propagates unchanged.
_CHAIN_RACE_CONSTRAINTS = ("uq_transitions_previous", "uq_transitions_head")


class ProcessLogRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_tail(
        self, subject_type: str, subject_id: int, flow: str
    ) -> Transition | None:
        """The chain's last row: the one no other row follows."""
        successor = aliased(Transition)
        return await self.db.scalar(
            select(Transition).where(
                Transition.subject_type == subject_type,
                Transition.subject_id == subject_id,
                Transition.flow == flow,
                ~exists().where(successor.previous_transition_id == Transition.id),
            )
        )

    async def get_chain(
        self, subject_type: str, subject_id: int, flow: str
    ) -> list[Transition]:
        """All rows of one chain, head first (``id`` order is chain order)."""
        result = await self.db.execute(
            select(Transition)
            .where(
                Transition.subject_type == subject_type,
                Transition.subject_id == subject_id,
                Transition.flow == flow,
            )
            .order_by(Transition.id)
        )
        return list(result.scalars().all())

    async def insert_transition(
        self,
        *,
        subject_type: str,
        subject_id: int,
        flow: str,
        previous_transition_id: int | None,
        from_status: str | None,
        to_status: str,
        source: str,
        actor_user_id: int | None,
        note: str | None,
        metadata: dict[str, Any] | None,
        snapshot_id: int | None,
        occurred_at: datetime | None,
    ) -> Transition:
        transition = Transition(
            subject_type=subject_type,
            subject_id=subject_id,
            flow=flow,
            previous_transition_id=previous_transition_id,
            from_status=from_status,
            to_status=to_status,
            source=source,
            actor_user_id=actor_user_id,
            note=note,
            metadata_=metadata,
            snapshot_id=snapshot_id,
        )
        # Left unset rather than None so the server default (now()) applies.
        if occurred_at is not None:
            transition.occurred_at = occurred_at
        self.db.add(transition)
        try:
            await self.db.flush()
        except IntegrityError as error:
            if any(name in str(error.orig) for name in _CHAIN_RACE_CONSTRAINTS):
                raise ConcurrentTransitionError(
                    subject_type, subject_id, flow
                ) from error
            raise
        return transition

    async def upsert_snapshot(
        self,
        *,
        subject_type: str,
        subject_id: int,
        schema_version: int,
        payload: dict[str, Any],
        payload_hash: str,
    ) -> int:
        """Id of the subject's snapshot with this hash, inserting it if new."""
        snapshot_id = await self.db.scalar(
            pg_insert(Snapshot)
            .values(
                subject_type=subject_type,
                subject_id=subject_id,
                schema_version=schema_version,
                payload=payload,
                payload_hash=payload_hash,
            )
            .on_conflict_do_nothing(constraint="uq_snapshots_subject_hash")
            .returning(Snapshot.id)
        )
        if snapshot_id is not None:
            return snapshot_id
        # DO NOTHING returns no row on conflict. The existing row is either
        # ours (inserted earlier in this transaction) or committed by another
        # one, which ON CONFLICT waited for, so this read sees it.
        return await self.db.scalar(
            select(Snapshot.id).where(
                Snapshot.subject_type == subject_type,
                Snapshot.subject_id == subject_id,
                Snapshot.payload_hash == payload_hash,
            )
        )
