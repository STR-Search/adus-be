"""Deal-status changes are written to the process log.

Covers the snapshot contents, each write path that logs (W1 deal-status PATCH,
W3 create, W4 duplicate), production wiring, and the 409 mapping. The process
log itself is a fake here; its SQL is covered in tests/core/process_log/.
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.process_log.enums import Flow, SubjectType, TransitionSource
from app.core.process_log.exceptions import ConcurrentTransitionError
from app.iron_bank.controllers.update_underwriting_controller import (
    UpdateUnderwritingController,
)
from app.iron_bank.enums import DealStatus
from app.iron_bank.models import Underwriting
from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload
from app.iron_bank.services.creation.duplicate_underwriting_service import (
    DuplicateUnderwritingService,
)
from app.iron_bank.services.deal_status_history import (
    UNDERWRITING_SNAPSHOT_VERSION,
    build_underwriting_snapshot,
)
from app.iron_bank.services.operations.save_underwriting_service import (
    SaveUnderwritingService,
)
from app.iron_bank.services.operations.update_underwriting_service import (
    UpdateUnderwritingService,
)


class FakeProcessLog:
    def __init__(self, events=None):
        self.calls: list[dict] = []
        self.events = events if events is not None else []

    async def record_transition(self, **kwargs):
        self.calls.append(kwargs)
        self.events.append("record")
        return len(self.calls)


def _underwriting(**overrides):
    base = dict(
        id=42,
        zpid="2078451",
        market_id=7,
        analyst_id=3,
        approver_id=None,
        owner_id=None,
        deal_status=DealStatus.ANALYST_COMPLETED,
        purchase_price=Decimal("525000.00"),
        total_oop=Decimal("182500.00"),
        m_cash_on_cash=Decimal("0.0841"),
        market_type=["mountain"],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ── Snapshot contents ────────────────────────────────────────────────────────


def test_snapshot_holds_full_deal_with_children_and_string_decimals():
    underwriting = _underwriting(
        taxes=SimpleNamespace(tax_savings=Decimal("41000.00")),
        operating_expenses=[
            SimpleNamespace(
                id=2, expense_name="Insurance", monthly_amount=Decimal("310.00")
            )
        ],
    )

    snapshot = build_underwriting_snapshot(underwriting)

    assert snapshot.schema_version == UNDERWRITING_SNAPSHOT_VERSION
    payload = snapshot.payload
    assert payload["id"] == 42
    assert payload["deal_status"] == "analyst_completed"
    assert payload["purchase_price"] == "525000.00"
    assert payload["total_oop"] == "182500.00"
    assert payload["m_cash_on_cash"] == "0.0841"
    assert payload["market_type"] == ["mountain"]
    assert payload["analyst_id"] == 3
    assert payload["taxes"]["tax_savings"] == "41000.00"
    assert payload["operating_expenses"][0]["expense_name"] == "Insurance"


def test_snapshot_excludes_resolved_fields_and_labels():
    payload = build_underwriting_snapshot(_underwriting()).payload

    for key in (
        "analyst",
        "approver",
        "owner",
        "realtor_details",
        "simulated",
        "discussion",
        "display_id",
    ):
        assert key not in payload
    assert not [key for key in payload if key.endswith("_label")]


def test_snapshot_is_stable_for_the_same_deal():
    assert (
        build_underwriting_snapshot(_underwriting()).payload
        == build_underwriting_snapshot(_underwriting()).payload
    )


# ── W1: PATCH /underwritings/{id}/deal-status ────────────────────────────────


class FakeRepo:
    def __init__(self, underwriting, events=None):
        self.underwriting = underwriting
        self.events = events if events is not None else []
        self.locked = False
        self.update_kwargs = None

    async def get_by_id(self, underwriting_id, *, for_update=False):
        self.locked = self.locked or for_update
        return self.underwriting

    async def update(self, underwriting_id, **kwargs):
        self.update_kwargs = kwargs
        for key, value in kwargs["underwriting_data"].items():
            setattr(self.underwriting, key, value)
        self.events.append("update")
        return self.underwriting

    async def commit(self):
        self.events.append("commit")


@pytest.mark.asyncio
async def test_status_change_is_logged_in_the_same_transaction():
    events: list[str] = []
    repository = FakeRepo(_underwriting(), events)
    process_log = FakeProcessLog(events)
    service = UpdateUnderwritingService(repository, process_log=process_log)

    await service.update_deal_status(
        underwriting_id=42,
        deal_status=DealStatus.PRESENT_TO_CLIENTS,
        actor_user_id=99,
    )

    assert repository.locked
    assert repository.update_kwargs["commit"] is False
    assert events == ["update", "record", "commit"]
    (call,) = process_log.calls
    assert call["subject_type"] == SubjectType.UNDERWRITING
    assert call["subject_id"] == 42
    assert call["flow"] == Flow.DEAL_STATUS
    assert call["expected_from_status"] == DealStatus.ANALYST_COMPLETED
    assert call["to_status"] == "present_to_clients"
    assert call["source"] == TransitionSource.API
    assert call["actor_user_id"] == 99
    # Snapshot is the state after the change.
    assert call["snapshot"].payload["deal_status"] == "present_to_clients"
    assert call["snapshot"].payload["approver_id"] == 99


@pytest.mark.asyncio
async def test_repeated_status_is_not_logged_but_still_commits():
    events: list[str] = []
    process_log = FakeProcessLog(events)
    service = UpdateUnderwritingService(
        FakeRepo(_underwriting(), events), process_log=process_log
    )

    await service.update_deal_status(
        underwriting_id=42,
        deal_status=DealStatus.ANALYST_COMPLETED,
        actor_user_id=99,
    )

    assert process_log.calls == []
    assert events == ["update", "commit"]


@pytest.mark.asyncio
async def test_log_failure_prevents_commit():
    events: list[str] = []

    class FailingLog(FakeProcessLog):
        async def record_transition(self, **kwargs):
            raise ConcurrentTransitionError("underwriting", 42, "deal_status")

    service = UpdateUnderwritingService(
        FakeRepo(_underwriting(), events), process_log=FailingLog()
    )

    with pytest.raises(ConcurrentTransitionError):
        await service.update_deal_status(
            underwriting_id=42,
            deal_status=DealStatus.MAYBE,
            actor_user_id=99,
        )
    assert "commit" not in events


@pytest.mark.asyncio
async def test_concurrent_transition_maps_to_409():
    class RacingService:
        async def update_deal_status(self, **kwargs):
            raise ConcurrentTransitionError("underwriting", 42, "deal_status")

    with pytest.raises(HTTPException) as error:
        await UpdateUnderwritingController(RacingService()).update_deal_status(
            underwriting_id=42, deal_status=DealStatus.MAYBE, actor_user_id=1
        )
    assert error.value.status_code == 409


# ── W3: create ───────────────────────────────────────────────────────────────


class FakeCreateRepo:
    def __init__(self, events):
        self.events = events
        self.create_kwargs = None

    async def create(self, **kwargs):
        self.create_kwargs = kwargs
        self.events.append("create")
        return _underwriting(
            deal_status=kwargs["underwriting_data"].get("deal_status"),
        )

    async def load_children(self, underwriting):
        self.events.append("load_children")

    async def commit(self):
        self.events.append("commit")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "log_source", [TransitionSource.API, TransitionSource.JOB]
)
async def test_create_writes_head_row_before_commit(log_source):
    events: list[str] = []
    repository = FakeCreateRepo(events)
    process_log = FakeProcessLog(events)
    service = SaveUnderwritingService(
        repository, process_log=process_log, log_source=log_source
    )

    await service.save(
        SaveUnderwritingPayload.model_validate(
            {"is_automated": False, "deal_status": "template_generated"}
        )
    )

    assert repository.create_kwargs["commit"] is False
    assert events == ["create", "load_children", "record", "commit"]
    (call,) = process_log.calls
    assert call["expected_from_status"] is None
    assert call["to_status"] == DealStatus.TEMPLATE_GENERATED
    assert call["source"] == log_source
    assert call["actor_user_id"] is None


@pytest.mark.asyncio
async def test_create_without_status_starts_no_chain():
    events: list[str] = []
    process_log = FakeProcessLog(events)
    service = SaveUnderwritingService(FakeCreateRepo(events), process_log=process_log)

    await service.save(SaveUnderwritingPayload.model_validate({"is_automated": False}))

    assert process_log.calls == []
    assert events == ["create", "commit"]


@pytest.mark.asyncio
async def test_create_without_process_log_commits_in_repository():
    events: list[str] = []
    repository = FakeCreateRepo(events)

    await SaveUnderwritingService(repository).save(
        SaveUnderwritingPayload.model_validate(
            {"is_automated": False, "deal_status": "template_generated"}
        )
    )

    assert repository.create_kwargs["commit"] is True
    assert events == ["create"]


# ── W4: duplicate ────────────────────────────────────────────────────────────


class FakeDuplicateRepo:
    def __init__(self, events, *, conflicts=0):
        self.events = events
        self.conflicts = conflicts
        self.create_commits = []
        self.source = Underwriting(
            id=5,
            series_id=uuid.uuid4(),
            version=0,
            deal_status=DealStatus.CLIENT_UNDER_CONTRACT.value,
        )

    async def get_by_id(self, underwriting_id):
        return self.source

    async def get_next_version_for_series(self, series_id):
        return 1

    async def create(self, underwriting_data, **children):
        self.create_commits.append(children.get("commit"))
        if self.conflicts:
            self.conflicts -= 1
            raise IntegrityError(
                "INSERT",
                {},
                Exception('unique constraint "uq_underwritings_series_version"'),
            )
        self.events.append("create")
        return Underwriting(
            id=77,
            series_id=underwriting_data["series_id"],
            version=underwriting_data["version"],
            deal_status=underwriting_data["deal_status"],
        )

    async def load_children(self, underwriting):
        self.events.append("load_children")

    async def commit(self):
        self.events.append("commit")


@pytest.mark.asyncio
async def test_duplicate_starts_copy_chain_at_template_generated():
    events: list[str] = []
    repository = FakeDuplicateRepo(events)
    process_log = FakeProcessLog(events)
    service = DuplicateUnderwritingService(repository, process_log=process_log)

    await service.duplicate(underwriting_id=5, current_user_id=8)

    assert repository.create_commits == [False]
    assert events == ["create", "load_children", "record", "commit"]
    (call,) = process_log.calls
    assert call["subject_id"] == 77
    assert call["expected_from_status"] is None
    assert call["to_status"] == DealStatus.TEMPLATE_GENERATED.value
    assert call["actor_user_id"] == 8
    assert call["metadata"] == {"copied_from_id": 5}


@pytest.mark.asyncio
async def test_duplicate_logs_once_after_version_conflict_retry():
    events: list[str] = []
    process_log = FakeProcessLog(events)
    service = DuplicateUnderwritingService(
        FakeDuplicateRepo(events, conflicts=1), process_log=process_log
    )

    await service.duplicate(underwriting_id=5, current_user_id=8)

    assert len(process_log.calls) == 1
    assert events == ["create", "load_children", "record", "commit"]


# ── Production wiring ────────────────────────────────────────────────────────


def test_router_wires_process_log_into_every_status_writer():
    from app.iron_bank import router

    db = object()
    update = router.get_update_underwriting_controller(db=db).service
    save = router.get_save_underwriting_controller(db=db).service
    duplicate = router.get_duplicate_underwriting_controller(db=db).service
    blank = router.get_create_blank_underwriting_controller(db=db).service.save_service
    from_url = router.get_create_underwriting_from_url_controller(
        db=db
    ).service.save_service

    for service in (update, save, duplicate, blank, from_url):
        assert service.process_log is not None
        # Same session as the status write, so both commit together.
        assert service.process_log.repository.db is service.repository.db


def test_batch_job_attributes_creates_to_job():
    from app.workflows.prepare_and_save_underwriting_job import (
        PrepareAndSaveUnderwritingJob,
    )

    save = PrepareAndSaveUnderwritingJob.from_session(object()).save_service

    assert save.process_log is not None
    assert save.log_source == TransitionSource.JOB
