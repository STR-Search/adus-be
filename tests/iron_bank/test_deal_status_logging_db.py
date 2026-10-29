"""Deal-status logging end to end against a real Postgres.

Opt-in: ``RUN_DB_TESTS=1 uv run pytest tests/iron_bank/test_deal_status_logging_db.py``.
Same guard and setup as tests/core/discussions/test_discussion_db.py (refuses
the production project). Each test creates its own underwritings and deletes
them, their children, and their process-log rows afterwards.

What the fakes in test_deal_status_logging.py cannot show: the real
``FOR UPDATE`` lock, children loading under asyncio after a flush, and the
composite chain FK accepting the rows the services write.
"""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.process_log.enums import Flow, SubjectType
from app.core.process_log.models import Snapshot, Transition
from app.core.process_log.repository import ProcessLogRepository
from app.core.process_log.service import ProcessLogService
from app.iron_bank.enums import DealStatus
from app.iron_bank.models import Underwriting
from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload
from app.iron_bank.services.creation.duplicate_underwriting_service import (
    DuplicateUnderwritingService,
)
from app.iron_bank.services.operations.save_underwriting_service import (
    SaveUnderwritingService,
)
from app.iron_bank.services.operations.update_underwriting_service import (
    UpdateUnderwritingService,
)
from tests.core.discussions.test_discussion_db import (  # noqa: F401 (fixture)
    USER_A,
    USER_B,
    pytestmark,
    sessionmaker,
)


def log_for(session) -> ProcessLogService:
    return ProcessLogService(ProcessLogRepository(session))


@pytest_asyncio.fixture
async def created(sessionmaker):  # noqa: F811
    """Collects underwriting ids made by a test; deletes them and their log."""
    ids: list[int] = []
    yield ids
    if ids:
        async with sessionmaker() as session:
            await session.execute(
                delete(Transition).where(
                    Transition.subject_type == SubjectType.UNDERWRITING.value,
                    Transition.subject_id.in_(ids),
                )
            )
            await session.execute(
                delete(Snapshot).where(
                    Snapshot.subject_type == SubjectType.UNDERWRITING.value,
                    Snapshot.subject_id.in_(ids),
                )
            )
            # Children cascade.
            await session.execute(delete(Underwriting).where(Underwriting.id.in_(ids)))
            await session.commit()


async def create_underwriting(sessionmaker, created) -> int:  # noqa: F811
    async with sessionmaker() as session:
        result = await SaveUnderwritingService(
            UnderwritingRepository(session), process_log=log_for(session)
        ).save(
            SaveUnderwritingPayload.model_validate(
                {
                    "is_automated": False,
                    "deal_status": "template_generated",
                    "purchase_price": "400000.00",
                    "operating_expenses": [
                        {"expense": "Insurance", "monthly": "300.00"}
                    ],
                }
            )
        )
    created.append(result.underwriting_id)
    return result.underwriting_id


async def set_status(sessionmaker, uw_id, status, actor=USER_A):  # noqa: F811
    async with sessionmaker() as session:
        await UpdateUnderwritingService(
            UnderwritingRepository(session), process_log=log_for(session)
        ).update_deal_status(
            underwriting_id=uw_id, deal_status=status, actor_user_id=actor
        )


async def history(sessionmaker, uw_id):  # noqa: F811
    async with sessionmaker() as session:
        return await log_for(session).get_history(
            SubjectType.UNDERWRITING, uw_id, Flow.DEAL_STATUS
        )


async def snapshot_payload(sessionmaker, snapshot_id) -> dict:  # noqa: F811
    async with sessionmaker() as session:
        return await session.scalar(
            select(Snapshot.payload).where(Snapshot.id == snapshot_id)
        )


@pytest.mark.asyncio
async def test_create_then_status_changes_build_the_chain(
    sessionmaker, created  # noqa: F811
):
    uw_id = await create_underwriting(sessionmaker, created)
    await set_status(sessionmaker, uw_id, DealStatus.ANALYST_STARTED)
    await set_status(sessionmaker, uw_id, DealStatus.ANALYST_STARTED)  # repeat
    await set_status(sessionmaker, uw_id, DealStatus.ANALYST_COMPLETED)

    rows = await history(sessionmaker, uw_id)
    assert [(r.from_status, r.to_status, r.source) for r in rows] == [
        (None, "template_generated", "api"),
        ("template_generated", "analyst_started", "api"),
        ("analyst_started", "analyst_completed", "api"),
    ]
    assert rows[0].actor_user_id is None
    assert rows[1].actor_user_id == USER_A

    # The head snapshot was built after a flush, so the children had to be
    # loaded explicitly; seeing them proves that worked under asyncio.
    head = await snapshot_payload(sessionmaker, rows[0].snapshot_id)
    assert head["purchase_price"] == "400000.00"
    assert head["operating_expenses"][0]["expense_name"] == "Insurance"
    assert head["deal_status"] == "template_generated"

    latest = await snapshot_payload(sessionmaker, rows[2].snapshot_id)
    assert latest["deal_status"] == "analyst_completed"
    assert latest["analyst_id"] == USER_A
    assert "analyst" not in latest


@pytest.mark.asyncio
async def test_duplicate_starts_its_own_chain(sessionmaker, created):  # noqa: F811
    source_id = await create_underwriting(sessionmaker, created)
    await set_status(sessionmaker, source_id, DealStatus.ANALYST_STARTED)

    async with sessionmaker() as session:
        result = await DuplicateUnderwritingService(
            UnderwritingRepository(session), process_log=log_for(session)
        ).duplicate(underwriting_id=source_id, current_user_id=USER_B)
    created.append(result.underwriting_id)

    (head,) = await history(sessionmaker, result.underwriting_id)
    assert (head.from_status, head.to_status) == (None, "template_generated")
    assert head.actor_user_id == USER_B
    assert head.metadata == {"copied_from_id": source_id}
    assert len(await history(sessionmaker, source_id)) == 2  # untouched


@pytest.mark.asyncio
async def test_concurrent_status_changes_serialize_without_forking(
    sessionmaker, created  # noqa: F811
):
    uw_id = await create_underwriting(sessionmaker, created)
    await set_status(sessionmaker, uw_id, DealStatus.ANALYST_STARTED)

    # Both start from analyst_started; the row lock makes the second wait and
    # then log from whatever the first one set.
    await asyncio.gather(
        set_status(sessionmaker, uw_id, DealStatus.ANALYST_COMPLETED),
        set_status(sessionmaker, uw_id, DealStatus.MAYBE),
    )

    rows = await history(sessionmaker, uw_id)
    assert len(rows) == 4
    for previous, row in zip(rows, rows[1:]):
        assert row.previous_transition_id == previous.id
        assert row.from_status == previous.to_status
    async with sessionmaker() as session:
        current = await session.scalar(
            select(Underwriting.deal_status).where(Underwriting.id == uw_id)
        )
    assert rows[-1].to_status == current


@pytest.mark.asyncio
async def test_failed_log_write_rolls_back_the_status_change(
    sessionmaker, created  # noqa: F811
):
    uw_id = await create_underwriting(sessionmaker, created)

    class BrokenLog:
        async def record_transition(self, **kwargs):
            raise RuntimeError("log unavailable")

    async with sessionmaker() as session:
        with pytest.raises(RuntimeError):
            await UpdateUnderwritingService(
                UnderwritingRepository(session), process_log=BrokenLog()
            ).update_deal_status(
                underwriting_id=uw_id,
                deal_status=DealStatus.ANALYST_STARTED,
                actor_user_id=USER_A,
            )
        await session.rollback()

    async with sessionmaker() as session:
        status = await session.scalar(
            select(Underwriting.deal_status).where(Underwriting.id == uw_id)
        )
    assert status == "template_generated"
    assert len(await history(sessionmaker, uw_id)) == 1
