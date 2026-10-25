"""ProcessLogService against an in-memory repository.

The fake mirrors the repository's chain semantics (tail = row nothing follows,
id order = chain order, snapshot dedupe per subject) so the service's
orchestration, including drift repair, is tested without a database. The SQL
is covered by test_process_log_repository_sql.py and test_process_log_db.py.
"""

from datetime import UTC, datetime
from decimal import Decimal
from itertools import count
from types import SimpleNamespace

import pytest

from app.core.process_log.enums import Flow, SubjectType, TransitionSource
from app.core.process_log.schemas import SnapshotInput
from app.core.process_log.service import (
    DRIFT_REPAIR_NOTE,
    ProcessLogService,
    payload_hash,
)

UW = SubjectType.UNDERWRITING
DEAL = Flow.DEAL_STATUS
API = TransitionSource.API


class FakeProcessLogRepository:
    def __init__(self):
        self.transitions: list[SimpleNamespace] = []
        self.snapshots: list[SimpleNamespace] = []
        self._ids = count(1)
        self._snapshot_ids = count(1)

    def _chain(self, subject_type, subject_id, flow):
        return [
            t
            for t in self.transitions
            if (t.subject_type, t.subject_id, t.flow)
            == (subject_type, subject_id, flow)
        ]

    async def get_tail(self, subject_type, subject_id, flow):
        chain = self._chain(subject_type, subject_id, flow)
        followed = {t.previous_transition_id for t in chain}
        tails = [t for t in chain if t.id not in followed]
        assert len(tails) <= 1, "chain forked"
        return tails[0] if tails else None

    async def get_chain(self, subject_type, subject_id, flow):
        return sorted(self._chain(subject_type, subject_id, flow), key=lambda t: t.id)

    async def insert_transition(self, **values):
        # Enforce the DB constraints the service relies on.
        assert (values["previous_transition_id"] is None) == (
            values["from_status"] is None
        )
        assert values["from_status"] != values["to_status"]
        if values["previous_transition_id"] is not None:
            previous = next(
                t for t in self.transitions if t.id == values["previous_transition_id"]
            )
            assert previous.to_status == values["from_status"]
            assert (previous.subject_type, previous.subject_id, previous.flow) == (
                values["subject_type"],
                values["subject_id"],
                values["flow"],
            )
        row = SimpleNamespace(
            id=next(self._ids),
            metadata_=values.pop("metadata"),
            **{k: v for k, v in values.items()},
        )
        if row.occurred_at is None:
            row.occurred_at = datetime(2026, 10, 26, tzinfo=UTC)
        self.transitions.append(row)
        return row

    async def upsert_snapshot(self, **values):
        for s in self.snapshots:
            if (s.subject_type, s.subject_id, s.payload_hash) == (
                values["subject_type"],
                values["subject_id"],
                values["payload_hash"],
            ):
                return s.id
        row = SimpleNamespace(id=next(self._snapshot_ids), **values)
        self.snapshots.append(row)
        return row.id


@pytest.fixture
def repo():
    return FakeProcessLogRepository()


@pytest.fixture
def service(repo):
    return ProcessLogService(repo)


async def record(service, expected, to, subject_id=1, **kwargs):
    return await service.record_transition(
        subject_type=UW,
        subject_id=subject_id,
        flow=DEAL,
        expected_from_status=expected,
        to_status=to,
        source=kwargs.pop("source", API),
        **kwargs,
    )


def statuses(repo, subject_id=1):
    return [
        (t.from_status, t.to_status, t.source)
        for t in sorted(repo.transitions, key=lambda t: t.id)
        if t.subject_id == subject_id
    ]


@pytest.mark.asyncio
async def test_head_then_appends(service, repo):
    await record(service, None, "template_generated", actor_user_id=4)
    await record(service, "template_generated", "analyst_started", actor_user_id=4)
    await record(service, "analyst_started", "analyst_completed")

    assert statuses(repo) == [
        (None, "template_generated", "api"),
        ("template_generated", "analyst_started", "api"),
        ("analyst_started", "analyst_completed", "api"),
    ]
    head, second, third = repo.transitions
    assert head.previous_transition_id is None
    assert second.previous_transition_id == head.id
    assert third.previous_transition_id == second.id
    assert head.actor_user_id == 4


@pytest.mark.asyncio
async def test_returns_id_of_real_row(service, repo):
    transition_id = await record(service, None, "template_generated")
    assert transition_id == repo.transitions[-1].id


@pytest.mark.asyncio
async def test_chains_are_per_subject(service, repo):
    await record(service, None, "template_generated", subject_id=1)
    await record(service, None, "template_generated", subject_id=2)
    await record(service, "template_generated", "maybe", subject_id=2)

    assert statuses(repo, 1) == [(None, "template_generated", "api")]
    assert statuses(repo, 2) == [
        (None, "template_generated", "api"),
        ("template_generated", "maybe", "api"),
    ]


@pytest.mark.asyncio
async def test_same_status_is_rejected(service, repo):
    await record(service, None, "maybe")
    with pytest.raises(ValueError, match="Not a transition"):
        await record(service, "maybe", "maybe")
    assert len(repo.transitions) == 1


@pytest.mark.asyncio
async def test_enum_and_string_inputs_are_stored_as_values(service, repo):
    await service.record_transition(
        subject_type="underwriting",
        subject_id=1,
        flow="deal_status",
        expected_from_status=None,
        to_status="maybe",
        source="job",
    )
    row = repo.transitions[0]
    assert (row.subject_type, row.flow, row.source) == (
        "underwriting",
        "deal_status",
        "job",
    )


@pytest.mark.asyncio
async def test_unknown_source_is_rejected(service):
    with pytest.raises(ValueError):
        await record(service, None, "maybe", source="cli")


@pytest.mark.asyncio
async def test_optional_fields_are_stored(service, repo):
    at = datetime(2025, 3, 14, tzinfo=UTC)
    await record(
        service,
        None,
        "present_to_clients",
        note="seeded",
        metadata={"copied_from_id": 9},
        occurred_at=at,
        source=TransitionSource.BACKFILL,
    )
    row = repo.transitions[0]
    assert row.note == "seeded"
    assert row.metadata_ == {"copied_from_id": 9}
    assert row.occurred_at == at


# ── Drift repair ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drift_inserts_system_repair_row_before_real_row(service, repo):
    await record(service, None, "analyst_started")
    # Status moved to analyst_completed outside the log (e.g. generic PATCH).
    real_id = await record(service, "analyst_completed", "present_to_clients")

    assert statuses(repo) == [
        (None, "analyst_started", "api"),
        ("analyst_started", "analyst_completed", "system"),
        ("analyst_completed", "present_to_clients", "api"),
    ]
    repair = repo.transitions[1]
    assert repair.note == DRIFT_REPAIR_NOTE
    assert repair.actor_user_id is None
    assert repair.snapshot_id is None
    assert real_id == repo.transitions[2].id


@pytest.mark.asyncio
async def test_drift_with_no_chain_makes_repair_row_the_head(service, repo):
    # A deal that predates the log and wasn't backfilled yet.
    await record(service, "analyst_completed", "present_to_clients")

    assert statuses(repo) == [
        (None, "analyst_completed", "system"),
        ("analyst_completed", "present_to_clients", "api"),
    ]


@pytest.mark.asyncio
async def test_status_cleared_outside_log_follows_old_tail(service, repo):
    await record(service, None, "maybe")
    # deal_status was set to NULL outside the log; a chain can't return to NULL.
    await record(service, None, "analyst_started")

    assert statuses(repo) == [
        (None, "maybe", "api"),
        ("maybe", "analyst_started", "api"),
    ]


@pytest.mark.asyncio
async def test_status_cleared_then_restored_adds_nothing(service, repo):
    head_id = await record(service, None, "maybe")
    assert await record(service, None, "maybe") == head_id
    assert len(repo.transitions) == 1


@pytest.mark.asyncio
async def test_drift_is_logged(service, repo, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.core.process_log.service.logger.warning",
        lambda event, **kw: calls.append((event, kw)),
    )
    await record(service, None, "maybe")
    await record(service, "analyst_started", "analyst_completed")

    assert calls == [
        (
            "process_log.drift_repaired",
            {
                "subject_type": "underwriting",
                "subject_id": 1,
                "flow": "deal_status",
                "logged_status": "maybe",
                "actual_status": "analyst_started",
            },
        )
    ]


# ── Snapshots ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_identical_snapshots_are_shared(service, repo):
    snap = SnapshotInput(1, {"market_id": 12, "purchase_price": "425000.00"})
    await record(service, None, "template_generated", snapshot=snap)
    await record(service, "template_generated", "analyst_started", snapshot=snap)
    changed = SnapshotInput(1, {"market_id": 12, "purchase_price": "450000.00"})
    await record(service, "analyst_started", "analyst_completed", snapshot=changed)

    assert len(repo.snapshots) == 2
    first, second, third = repo.transitions
    assert first.snapshot_id == second.snapshot_id != third.snapshot_id


@pytest.mark.asyncio
async def test_snapshot_dedupe_is_per_subject(service, repo):
    snap = SnapshotInput(1, {"market_id": 12})
    await record(service, None, "maybe", subject_id=1, snapshot=snap)
    await record(service, None, "maybe", subject_id=2, snapshot=snap)

    assert len(repo.snapshots) == 2


@pytest.mark.asyncio
async def test_no_snapshot_leaves_snapshot_id_null(service, repo):
    await record(service, None, "maybe")
    assert repo.transitions[0].snapshot_id is None
    assert repo.snapshots == []


def test_payload_hash_ignores_key_order():
    assert payload_hash({"a": 1, "b": "x"}) == payload_hash({"b": "x", "a": 1})


def test_payload_hash_changes_with_values():
    assert payload_hash({"a": 1}) != payload_hash({"a": 2})


def test_payload_hash_rejects_non_json_values():
    with pytest.raises(TypeError):
        payload_hash({"price": Decimal("1.00")})


# ── History ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_history_returns_chain_in_order(service, repo):
    await record(service, None, "template_generated", metadata={"k": 1})
    await record(service, "template_generated", "analyst_started")

    history = await service.get_history(UW, 1, DEAL)

    assert [(h.from_status, h.to_status) for h in history] == [
        (None, "template_generated"),
        ("template_generated", "analyst_started"),
    ]
    assert history[0].metadata == {"k": 1}
    assert history[1].previous_transition_id == history[0].id
