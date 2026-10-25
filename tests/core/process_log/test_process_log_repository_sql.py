"""Compile-level checks for the repository's non-trivial SQL.

No database: a capturing session records each statement and it is compiled
with the PostgreSQL dialect. Behaviour against a real database is covered by
test_process_log_db.py.
"""

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.core.process_log.exceptions import ConcurrentTransitionError
from app.core.process_log.repository import ProcessLogRepository


class _Result:
    def scalars(self):
        return self

    def all(self):
        return []


class CapturingSession:
    def __init__(self, scalar_results=(), flush_error=None):
        self.statements = []
        self.added = []
        self._scalar_results = list(scalar_results)
        self._flush_error = flush_error

    async def execute(self, statement, params=None):
        self.statements.append(statement)
        return _Result()

    async def scalar(self, statement):
        self.statements.append(statement)
        return self._scalar_results.pop(0) if self._scalar_results else None

    def add(self, instance):
        self.added.append(instance)

    async def flush(self):
        if self._flush_error is not None:
            raise self._flush_error


def sql(statement) -> str:
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


def insert_kwargs(**overrides):
    values = {
        "subject_type": "underwriting",
        "subject_id": 7,
        "flow": "deal_status",
        "previous_transition_id": None,
        "from_status": None,
        "to_status": "maybe",
        "source": "api",
        "actor_user_id": None,
        "note": None,
        "metadata": None,
        "snapshot_id": None,
        "occurred_at": None,
    }
    values.update(overrides)
    return values


def integrity_error(constraint: str) -> IntegrityError:
    return IntegrityError(
        "INSERT ...",
        {},
        Exception(f'duplicate key value violates unique constraint "{constraint}"'),
    )


@pytest.mark.asyncio
async def test_get_tail_is_anti_join_on_successor():
    session = CapturingSession()
    await ProcessLogRepository(session).get_tail("underwriting", 7, "deal_status")
    stmt = sql(session.statements[0])
    assert "FROM process_log.transitions WHERE" in stmt
    assert "NOT (EXISTS (SELECT * FROM process_log.transitions AS transitions_1" in stmt
    assert (
        "transitions_1.previous_transition_id = process_log.transitions.id" in stmt
    )


@pytest.mark.asyncio
async def test_get_chain_orders_by_id():
    session = CapturingSession()
    await ProcessLogRepository(session).get_chain("underwriting", 7, "deal_status")
    assert sql(session.statements[0]).endswith(
        "ORDER BY process_log.transitions.id"
    )


@pytest.mark.asyncio
async def test_insert_transition_maps_metadata_and_keeps_server_default():
    session = CapturingSession()
    row = await ProcessLogRepository(session).insert_transition(
        **insert_kwargs(metadata={"copied_from_id": 3})
    )
    assert session.added == [row]
    assert row.metadata_ == {"copied_from_id": 3}
    # Unset (not None) so INSERT omits it and now() applies.
    assert "occurred_at" not in row.__dict__


@pytest.mark.asyncio
@pytest.mark.parametrize("constraint", ["uq_transitions_previous", "uq_transitions_head"])
async def test_chain_race_becomes_concurrent_transition_error(constraint):
    session = CapturingSession(flush_error=integrity_error(constraint))
    with pytest.raises(ConcurrentTransitionError):
        await ProcessLogRepository(session).insert_transition(**insert_kwargs())


@pytest.mark.asyncio
async def test_other_integrity_errors_propagate():
    session = CapturingSession(flush_error=integrity_error("fk_transitions_previous"))
    with pytest.raises(IntegrityError):
        await ProcessLogRepository(session).insert_transition(**insert_kwargs())


@pytest.mark.asyncio
async def test_upsert_snapshot_inserts_on_conflict_do_nothing():
    session = CapturingSession(scalar_results=[41])
    snapshot_id = await ProcessLogRepository(session).upsert_snapshot(
        subject_type="underwriting",
        subject_id=7,
        schema_version=1,
        payload={"market_id": 1},
        payload_hash="abc",
    )
    assert snapshot_id == 41
    assert len(session.statements) == 1
    stmt = sql(session.statements[0])
    assert "ON CONFLICT ON CONSTRAINT uq_snapshots_subject_hash DO NOTHING" in stmt
    assert stmt.endswith("RETURNING process_log.snapshots.id")


@pytest.mark.asyncio
async def test_upsert_snapshot_reads_existing_on_conflict():
    session = CapturingSession(scalar_results=[None, 17])
    snapshot_id = await ProcessLogRepository(session).upsert_snapshot(
        subject_type="underwriting",
        subject_id=7,
        schema_version=1,
        payload={"market_id": 1},
        payload_hash="abc",
    )
    assert snapshot_id == 17
    lookup = sql(session.statements[1])
    assert lookup.startswith("SELECT process_log.snapshots.id FROM process_log.snapshots")
    assert "process_log.snapshots.payload_hash = " in lookup
