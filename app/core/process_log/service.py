"""``ProcessLogService``: the only entry point for domains.

Methods never commit. The caller owns the transaction so a transition lands
atomically with the status change it records.
"""

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.core.logger import logger
from app.core.process_log.enums import Flow, SubjectType, TransitionSource
from app.core.process_log.repository import ProcessLogRepository
from app.core.process_log.schemas import SnapshotInput, TransitionRead

DRIFT_REPAIR_NOTE = "drift repair"


def payload_hash(payload: Mapping[str, Any]) -> str:
    """SHA-256 of the canonical JSON form (sorted keys, no whitespace).

    Raises ``TypeError`` for values that are not JSON-ready (e.g. ``Decimal``):
    the producer must serialize them, or the hash would not be stable.
    """
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class ProcessLogService:
    def __init__(self, repository: ProcessLogRepository):
        self.repository = repository

    async def record_transition(
        self,
        *,
        subject_type: SubjectType,
        subject_id: int,
        flow: Flow,
        expected_from_status: str | None,
        to_status: str,
        source: TransitionSource,
        actor_user_id: int | None = None,
        note: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        snapshot: SnapshotInput | None = None,
        occurred_at: datetime | None = None,
    ) -> int:
        """Append ``expected_from_status → to_status`` to the subject's chain.

        ``expected_from_status`` is the status the caller saw on its (locked)
        row before changing it; ``None`` for a newly created subject. If the
        chain's tail disagrees, the log missed a change, so a ``system`` repair
        row bridges the gap before the real row is written. Returns the id of
        the real row.
        """
        if expected_from_status == to_status:
            raise ValueError(
                f"Not a transition: {flow} is already {to_status!r} "
                f"for {subject_type} {subject_id}"
            )
        subject_type = SubjectType(subject_type).value
        flow = Flow(flow).value

        tail = await self.repository.get_tail(subject_type, subject_id, flow)
        tail_status = tail.to_status if tail is not None else None

        if tail_status != expected_from_status:
            logger.warning(
                "process_log.drift_repaired",
                subject_type=subject_type,
                subject_id=subject_id,
                flow=flow,
                logged_status=tail_status,
                actual_status=expected_from_status,
            )
            if expected_from_status is None:
                # The subject's status was cleared outside the log. A chain
                # cannot return to NULL, so the real row follows the old tail,
                # and if it restores that same status there is nothing to add.
                expected_from_status = tail_status
                if tail_status == to_status:
                    return tail.id
            else:
                tail = await self.repository.insert_transition(
                    subject_type=subject_type,
                    subject_id=subject_id,
                    flow=flow,
                    previous_transition_id=tail.id if tail is not None else None,
                    from_status=tail_status,
                    to_status=expected_from_status,
                    source=TransitionSource.SYSTEM.value,
                    actor_user_id=None,
                    note=DRIFT_REPAIR_NOTE,
                    metadata=None,
                    snapshot_id=None,
                    occurred_at=None,
                )

        snapshot_id = (
            await self._upsert_snapshot(subject_type, subject_id, snapshot)
            if snapshot is not None
            else None
        )
        transition = await self.repository.insert_transition(
            subject_type=subject_type,
            subject_id=subject_id,
            flow=flow,
            previous_transition_id=tail.id if tail is not None else None,
            from_status=expected_from_status,
            to_status=to_status,
            source=TransitionSource(source).value,
            actor_user_id=actor_user_id,
            note=note,
            metadata=dict(metadata) if metadata is not None else None,
            snapshot_id=snapshot_id,
            occurred_at=occurred_at,
        )
        return transition.id

    async def get_history(
        self, subject_type: SubjectType, subject_id: int, flow: Flow
    ) -> list[TransitionRead]:
        """The subject's chain for ``flow``, oldest first."""
        rows = await self.repository.get_chain(
            SubjectType(subject_type).value, subject_id, Flow(flow).value
        )
        return [TransitionRead.model_validate(row) for row in rows]

    async def _upsert_snapshot(
        self, subject_type: str, subject_id: int, snapshot: SnapshotInput
    ) -> int:
        payload = dict(snapshot.payload)
        return await self.repository.upsert_snapshot(
            subject_type=subject_type,
            subject_id=subject_id,
            schema_version=snapshot.schema_version,
            payload=payload,
            payload_hash=payload_hash(payload),
        )
