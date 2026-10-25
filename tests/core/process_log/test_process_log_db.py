"""ProcessLogService + ProcessLogRepository against a real Postgres.

Opt-in: ``RUN_DB_TESTS=1 uv run pytest tests/core/process_log/test_process_log_db.py``.
Uses ``DATABASE_URL`` and refuses to run against the production project.
Requires the process_log migrations and user 1. Each test uses fresh random
subject ids and deletes its rows afterwards.
"""

import os
import random
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_config
from app.core.process_log.enums import Flow, SubjectType, TransitionSource
from app.core.process_log.exceptions import ConcurrentTransitionError
from app.core.process_log.models import Snapshot, Transition
from app.core.process_log.repository import ProcessLogRepository
from app.core.process_log.schemas import SnapshotInput
from app.core.process_log.service import ProcessLogService

PROD_PROJECT_REF = "cnunaeslrrgetewuxsty"
USER_A = 1
UW = SubjectType.UNDERWRITING.value
DEAL = Flow.DEAL_STATUS.value

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="set RUN_DB_TESTS=1 to run"
)


@pytest_asyncio.fixture
async def sessionmaker():
    url = get_config().async_database_url
    if PROD_PROJECT_REF in url:
        pytest.fail("Refusing to run DB tests against the production project")
    engine = create_async_engine(
        url,
        pool_size=3,
        connect_args={
            "prepared_statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__t_{os.urandom(8).hex()}__",
            "statement_cache_size": 0,
        },
    )
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def subjects(sessionmaker):
    """Hands out unused subject ids; deletes their rows afterwards."""
    ids: list[int] = []

    def new() -> int:
        # Far above real underwriting ids so tests never touch real history.
        ids.append(random.randint(10**12, 10**13))
        return ids[-1]

    yield new
    if ids:
        async with sessionmaker() as session:
            # One statement per table: NO ACTION lets a whole chain go at once.
            await session.execute(
                delete(Transition).where(Transition.subject_id.in_(ids))
            )
            await session.execute(delete(Snapshot).where(Snapshot.subject_id.in_(ids)))
            await session.commit()


async def record(sessionmaker, subject_id, expected, to, **kwargs) -> int:
    async with sessionmaker() as session:
        transition_id = await ProcessLogService(
            ProcessLogRepository(session)
        ).record_transition(
            subject_type=SubjectType.UNDERWRITING,
            subject_id=subject_id,
            flow=Flow.DEAL_STATUS,
            expected_from_status=expected,
            to_status=to,
            source=kwargs.pop("source", TransitionSource.API),
            **kwargs,
        )
        await session.commit()
    return transition_id


async def chain(sessionmaker, subject_id) -> list[Transition]:
    async with sessionmaker() as session:
        return await ProcessLogRepository(session).get_chain(UW, subject_id, DEAL)


async def raw_insert(sessionmaker, subject_id, **overrides):
    """Insert through the repository, bypassing the service's checks."""
    values = {
        "subject_type": UW,
        "subject_id": subject_id,
        "flow": DEAL,
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
    async with sessionmaker() as session:
        row = await ProcessLogRepository(session).insert_transition(**values)
        await session.commit()
    return row


# ── Service round trip ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_round_trip(sessionmaker, subjects):
    sid = subjects()
    snap = SnapshotInput(1, {"market_id": 12, "purchase_price": "425000.00"})
    await record(sessionmaker, sid, None, "template_generated", snapshot=snap)
    await record(
        sessionmaker,
        sid,
        "template_generated",
        "analyst_started",
        actor_user_id=USER_A,
        snapshot=snap,
        metadata={"k": 1},
    )

    head, second = await chain(sessionmaker, sid)
    assert (head.from_status, head.to_status) == (None, "template_generated")
    assert second.previous_transition_id == head.id
    assert second.from_status == "template_generated"
    assert second.actor_user_id == USER_A
    assert second.metadata_ == {"k": 1}
    assert head.occurred_at.tzinfo is not None  # server default applied
    # Same payload → one snapshot row, shared.
    assert head.snapshot_id == second.snapshot_id is not None


@pytest.mark.asyncio
async def test_explicit_occurred_at_is_kept(sessionmaker, subjects):
    sid = subjects()
    at = datetime(2025, 3, 14, 10, 22, tzinfo=UTC)
    await record(
        sessionmaker,
        sid,
        None,
        "present_to_clients",
        occurred_at=at,
        source=TransitionSource.BACKFILL,
    )
    (row,) = await chain(sessionmaker, sid)
    assert row.occurred_at == at
    assert row.source == "backfill"


@pytest.mark.asyncio
async def test_drift_repair(sessionmaker, subjects):
    sid = subjects()
    await record(sessionmaker, sid, None, "analyst_started")
    await record(sessionmaker, sid, "analyst_completed", "present_to_clients")

    rows = await chain(sessionmaker, sid)
    assert [(r.from_status, r.to_status, r.source) for r in rows] == [
        (None, "analyst_started", "api"),
        ("analyst_started", "analyst_completed", "system"),
        ("analyst_completed", "present_to_clients", "api"),
    ]


@pytest.mark.asyncio
async def test_service_never_commits(sessionmaker, subjects):
    sid = subjects()
    async with sessionmaker() as session:
        await ProcessLogService(ProcessLogRepository(session)).record_transition(
            subject_type=SubjectType.UNDERWRITING,
            subject_id=sid,
            flow=Flow.DEAL_STATUS,
            expected_from_status=None,
            to_status="maybe",
            source=TransitionSource.API,
            snapshot=SnapshotInput(1, {"market_id": 1}),
        )
        await session.rollback()

    async with sessionmaker() as session:
        assert await chain(sessionmaker, sid) == []
        assert (
            await session.scalar(
                select(func.count()).where(Snapshot.subject_id == sid)
            )
            == 0
        )


# ── Constraints ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_second_head_is_a_concurrent_transition(sessionmaker, subjects):
    sid = subjects()
    await raw_insert(sessionmaker, sid)
    with pytest.raises(ConcurrentTransitionError):
        await raw_insert(sessionmaker, sid, to_status="analyst_started")


@pytest.mark.asyncio
async def test_fork_is_a_concurrent_transition(sessionmaker, subjects):
    sid = subjects()
    head = await raw_insert(sessionmaker, sid)
    follow = {"previous_transition_id": head.id, "from_status": "maybe"}
    await raw_insert(sessionmaker, sid, to_status="analyst_started", **follow)
    with pytest.raises(ConcurrentTransitionError):
        await raw_insert(sessionmaker, sid, to_status="delete_deal", **follow)


@pytest.mark.asyncio
async def test_cannot_follow_another_subjects_row(sessionmaker, subjects):
    other_head = await raw_insert(sessionmaker, subjects())
    with pytest.raises(IntegrityError, match="fk_transitions_previous"):
        await raw_insert(
            sessionmaker,
            subjects(),
            previous_transition_id=other_head.id,
            from_status="maybe",
            to_status="analyst_started",
        )


@pytest.mark.asyncio
async def test_from_status_must_match_previous_to_status(sessionmaker, subjects):
    sid = subjects()
    head = await raw_insert(sessionmaker, sid)  # → maybe
    with pytest.raises(IntegrityError, match="fk_transitions_previous"):
        await raw_insert(
            sessionmaker,
            sid,
            previous_transition_id=head.id,
            from_status="analyst_started",
            to_status="analyst_completed",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides, constraint",
    [
        ({"from_status": "maybe", "to_status": "delete_deal"}, "ck_transitions_head_has_no_from"),
        ({"source": "cli"}, "ck_transitions_source"),
    ],
)
async def test_check_constraints(sessionmaker, subjects, overrides, constraint):
    with pytest.raises(IntegrityError, match=constraint):
        await raw_insert(sessionmaker, subjects(), **overrides)


@pytest.mark.asyncio
async def test_non_head_needs_from_status_and_a_change(sessionmaker, subjects):
    sid = subjects()
    head = await raw_insert(sessionmaker, sid)
    with pytest.raises(IntegrityError, match="ck_transitions_head_has_no_from"):
        await raw_insert(sessionmaker, sid, previous_transition_id=head.id)
    with pytest.raises(IntegrityError, match="ck_transitions_changes_status"):
        await raw_insert(
            sessionmaker,
            sid,
            previous_transition_id=head.id,
            from_status="maybe",
            to_status="maybe",
        )


@pytest.mark.asyncio
async def test_middle_row_cannot_be_deleted_alone(sessionmaker, subjects):
    sid = subjects()
    await record(sessionmaker, sid, None, "template_generated")
    await record(sessionmaker, sid, "template_generated", "analyst_started")
    head, _ = await chain(sessionmaker, sid)

    async with sessionmaker() as session:
        with pytest.raises(IntegrityError, match="fk_transitions_previous"):
            await session.execute(delete(Transition).where(Transition.id == head.id))
        await session.rollback()


# ── Seeding (backfill) ───────────────────────────────────────────────────────


def head_seed(subject_id, **kwargs):
    from app.core.process_log.schemas import HeadSeed

    return HeadSeed(
        subject_type=UW,
        subject_id=subject_id,
        flow=DEAL,
        to_status=kwargs.pop("to_status", "maybe"),
        source="backfill",
        snapshot=kwargs.pop("snapshot", SnapshotInput(1, {"s": subject_id})),
        **kwargs,
    )


async def seed(sessionmaker, seeds) -> int:
    async with sessionmaker() as session:
        inserted = await ProcessLogService(ProcessLogRepository(session)).seed_heads(
            seeds
        )
        await session.commit()
    return inserted


@pytest.mark.asyncio
async def test_seed_heads_is_idempotent_and_skips_existing_chains(
    sessionmaker, subjects
):
    fresh, live = subjects(), subjects()
    at = datetime(2025, 3, 14, tzinfo=UTC)
    # `live` already has history from the normal write path.
    await record(sessionmaker, live, None, "analyst_started")

    seeds = [head_seed(fresh, occurred_at=at, actor_user_id=USER_A), head_seed(live)]
    assert await seed(sessionmaker, seeds) == 1
    assert await seed(sessionmaker, seeds) == 0  # rerun

    (row,) = await chain(sessionmaker, fresh)
    assert (row.from_status, row.to_status, row.source) == (None, "maybe", "backfill")
    assert row.occurred_at == at
    assert row.actor_user_id == USER_A
    assert row.snapshot_id is not None
    # The live chain is untouched.
    assert [r.to_status for r in await chain(sessionmaker, live)] == ["analyst_started"]


@pytest.mark.asyncio
async def test_seed_heads_defaults_occurred_at_to_now(sessionmaker, subjects):
    sid = subjects()
    assert await seed(sessionmaker, [head_seed(sid, snapshot=None)]) == 1
    (row,) = await chain(sessionmaker, sid)
    assert row.occurred_at.tzinfo is not None
    assert row.snapshot_id is None
