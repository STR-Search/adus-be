"""Duplicate-email handling for the realtors CRUD path.

Realtor identity is the email, enforced by ``uq_realtors_email_active`` as a
partial functional unique index on ``lower(btrim(email))``. These tests cover
the translation of the resulting IntegrityError into a 409 that names the
existing row, rather than the bare 500 the controller used to return.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.markets.controllers.realtor_controller import RealtorController
from app.markets.schemas.realtor import RealtorCreateSchema, RealtorUpdateSchema
from app.markets.services.realtor_service import (
    DuplicateRealtorEmailError,
    RealtorService,
)


def _realtor(record_id: int, *, email: str | None = "jane@example.com", **overrides):
    base = dict(
        id=record_id,
        name=f"Realtor {record_id}",
        email=email,
        phone=None,
        brokerage=None,
        notes=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class StubRepository:
    """In-memory stand-in that matches emails the way the unique index does."""

    def __init__(self, rows=None, *, conflict=False):
        self._rows = rows or []
        self._conflict = conflict
        self.rolled_back = False
        # The service reaches through to roll back a failed write.
        self.db = SimpleNamespace(rollback=self._rollback)

    async def _rollback(self):
        self.rolled_back = True

    async def get_by_id(self, record_id):
        return next((row for row in self._rows if row.id == record_id), None)

    async def get_active_by_email(self, email):
        if email is None or not email.strip():
            return None
        needle = email.strip().lower()
        return next(
            (
                row
                for row in self._rows
                if row.email and row.email.strip().lower() == needle
            ),
            None,
        )

    async def create(self, data):
        if self._conflict:
            raise IntegrityError("insert", {}, Exception("unique violation"))
        row = _realtor(99, **data)
        self._rows.append(row)
        return row

    async def update(self, record_id, data):
        if self._conflict:
            raise IntegrityError("update", {}, Exception("unique violation"))
        row = await self.get_by_id(record_id)
        if row is None:
            return None
        for field, value in data.items():
            setattr(row, field, value)
        return row


@pytest.mark.asyncio
async def test_create_returns_the_new_realtor_when_the_email_is_free():
    service = RealtorService(StubRepository())

    created = await service.create(
        RealtorCreateSchema(name="Jane R", email="jane@example.com")
    )

    assert created.email == "jane@example.com"


@pytest.mark.asyncio
async def test_duplicate_create_rolls_back_and_reports_the_existing_id():
    repository = StubRepository([_realtor(5)], conflict=True)
    service = RealtorService(repository)

    with pytest.raises(DuplicateRealtorEmailError) as excinfo:
        await service.create(RealtorCreateSchema(email="jane@example.com"))

    assert excinfo.value.existing_id == 5
    assert repository.rolled_back is True


@pytest.mark.asyncio
@pytest.mark.parametrize("email", ["JANE@EXAMPLE.COM", "  jane@example.com  "])
async def test_existing_row_is_found_regardless_of_case_or_padding(email):
    """The lookup has to mirror lower(btrim(email)) or the 409 would come back
    with a null existing_id even though a conflicting row plainly exists."""
    repository = StubRepository([_realtor(5)], conflict=True)
    service = RealtorService(repository)

    with pytest.raises(DuplicateRealtorEmailError) as excinfo:
        await service.create(RealtorCreateSchema(email=email))

    assert excinfo.value.existing_id == 5


@pytest.mark.asyncio
async def test_duplicate_update_rolls_back_and_reports_the_existing_id():
    repository = StubRepository(
        [_realtor(5), _realtor(6, email="other@example.com")], conflict=True
    )
    service = RealtorService(repository)

    with pytest.raises(DuplicateRealtorEmailError) as excinfo:
        await service.update(6, RealtorUpdateSchema(email="jane@example.com"))

    assert excinfo.value.existing_id == 5
    assert repository.rolled_back is True


@pytest.mark.asyncio
async def test_a_conflict_with_no_findable_row_still_raises_with_a_null_id():
    """The row could have been soft-deleted between the failed insert and the
    lookup; the client still gets a 409, just without an id to follow."""
    repository = StubRepository(conflict=True)
    service = RealtorService(repository)

    with pytest.raises(DuplicateRealtorEmailError) as excinfo:
        await service.create(RealtorCreateSchema(email="jane@example.com"))

    assert excinfo.value.existing_id is None


@pytest.mark.asyncio
async def test_controller_turns_a_duplicate_create_into_a_409():
    controller = RealtorController(
        RealtorService(StubRepository([_realtor(5)], conflict=True))
    )

    with pytest.raises(HTTPException) as excinfo:
        await controller.create(RealtorCreateSchema(email="jane@example.com"))

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["existing_id"] == 5
    assert "already exists" in excinfo.value.detail["message"]


@pytest.mark.asyncio
async def test_controller_turns_a_duplicate_update_into_a_409():
    controller = RealtorController(
        RealtorService(StubRepository([_realtor(5), _realtor(6)], conflict=True))
    )

    with pytest.raises(HTTPException) as excinfo:
        await controller.update(6, RealtorUpdateSchema(email="jane@example.com"))

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["existing_id"] == 5


@pytest.mark.asyncio
async def test_a_missing_realtor_on_update_is_still_a_404_not_a_409():
    controller = RealtorController(RealtorService(StubRepository()))

    with pytest.raises(HTTPException) as excinfo:
        await controller.update(404, RealtorUpdateSchema(name="Nobody"))

    assert excinfo.value.status_code == 404
