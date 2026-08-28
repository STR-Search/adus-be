from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.users.controllers.saved_search_controller import SavedSearchController
from app.users.schemas.saved_search import (
    CreateSavedSearchPayload,
    UpdateSavedSearchPayload,
)
from app.users.services.saved_search_service import (
    DuplicateSavedSearchNameError,
    SavedSearchService,
)

RESOURCE = "iron_bank.underwritings"


def _saved_search(saved_search_id: int, *, user_id: int = 1, **overrides):
    base = dict(
        id=saved_search_id,
        user_id=user_id,
        resource=RESOURCE,
        name=f"search {saved_search_id}",
        filters={"bedrooms": 3},
        query_string="?bedrooms=3",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class StubRepository:
    """In-memory stand-in that enforces the same user scoping as the real one."""

    def __init__(self, rows=None, *, create_conflict=False, error=None):
        self._rows = rows or []
        self._create_conflict = create_conflict
        self._error = error
        self.rolled_back = False
        self.deleted = []
        # The service reaches through to roll back a failed insert.
        self.db = SimpleNamespace(rollback=self._rollback)

    async def _rollback(self):
        self.rolled_back = True

    async def list_by_user(self, *, user_id, resource=None):
        if self._error is not None:
            raise self._error
        return [
            row
            for row in self._rows
            if row.user_id == user_id
            and (resource is None or row.resource == resource)
        ]

    async def get_by_id_for_user(self, *, saved_search_id, user_id):
        for row in self._rows:
            if row.id == saved_search_id and row.user_id == user_id:
                return row
        return None

    async def get_by_name_for_user(self, *, user_id, resource, name):
        for row in self._rows:
            if (
                row.user_id == user_id
                and row.resource == resource
                and row.name == name
            ):
                return row
        return None

    async def create(self, *, user_id, resource, name, filters, query_string):
        if self._create_conflict:
            raise IntegrityError("insert", {}, Exception("unique violation"))
        row = _saved_search(
            99,
            user_id=user_id,
            resource=resource,
            name=name,
            filters=filters,
            query_string=query_string,
        )
        self._rows.append(row)
        return row

    async def update(self, saved_search, changes):
        for field, value in changes.items():
            setattr(saved_search, field, value)
        return saved_search

    async def delete(self, saved_search):
        self.deleted.append(saved_search.id)


@pytest.mark.asyncio
async def test_list_is_scoped_to_the_user_and_resource():
    rows = [
        _saved_search(1, user_id=1),
        _saved_search(2, user_id=1, resource="markets.opex"),
        _saved_search(3, user_id=2),
    ]
    service = SavedSearchService(StubRepository(rows))

    mine = await service.list_for_user(user_id=1, resource=RESOURCE)

    assert [row.id for row in mine] == [1]


@pytest.mark.asyncio
async def test_create_persists_filters_and_query_string():
    service = SavedSearchService(StubRepository())
    payload = CreateSavedSearchPayload(
        resource=RESOURCE,
        name="Austin 3BR",
        filters={"bedrooms": 3, "market_id": [7]},
        query_string="?bedrooms=3&market_id=7",
    )

    created = await service.create(user_id=1, payload=payload)

    assert created.filters == {"bedrooms": 3, "market_id": [7]}
    assert created.query_string == "?bedrooms=3&market_id=7"


@pytest.mark.asyncio
async def test_duplicate_name_rolls_back_and_reports_the_existing_id():
    existing = _saved_search(5, name="Austin 3BR")
    repository = StubRepository([existing], create_conflict=True)
    service = SavedSearchService(repository)
    payload = CreateSavedSearchPayload(
        resource=RESOURCE, name="Austin 3BR", filters={}
    )

    with pytest.raises(DuplicateSavedSearchNameError) as excinfo:
        await service.create(user_id=1, payload=payload)

    assert excinfo.value.existing_id == 5
    assert repository.rolled_back is True


@pytest.mark.asyncio
async def test_duplicate_name_surfaces_as_409_with_the_existing_id():
    repository = StubRepository([_saved_search(5, name="Austin 3BR")], create_conflict=True)
    controller = SavedSearchController(SavedSearchService(repository))
    payload = CreateSavedSearchPayload(
        resource=RESOURCE, name="Austin 3BR", filters={}
    )

    with pytest.raises(HTTPException) as excinfo:
        await controller.create_saved_search(user_id=1, payload=payload)

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["existing_id"] == 5


@pytest.mark.asyncio
async def test_patch_only_applies_fields_that_were_sent():
    row = _saved_search(1, name="old", query_string="?bedrooms=3")
    service = SavedSearchService(StubRepository([row]))

    updated = await service.update(
        saved_search=row, payload=UpdateSavedSearchPayload(name="new")
    )

    assert updated.name == "new"
    # Omitted, so untouched — not overwritten with the field default.
    assert updated.query_string == "?bedrooms=3"
    assert updated.filters == {"bedrooms": 3}


@pytest.mark.asyncio
async def test_patch_with_explicit_null_clears_query_string():
    row = _saved_search(1, query_string="?bedrooms=3")
    service = SavedSearchService(StubRepository([row]))

    updated = await service.update(
        saved_search=row,
        payload=UpdateSavedSearchPayload.model_validate({"query_string": None}),
    )

    assert updated.query_string is None


@pytest.mark.parametrize("field", ["name", "filters"])
def test_patch_rejects_explicit_null_on_not_null_columns(field):
    with pytest.raises(ValidationError):
        UpdateSavedSearchPayload.model_validate({field: None})


@pytest.mark.asyncio
async def test_filters_may_be_a_top_level_array_of_conditions():
    service = SavedSearchService(StubRepository())
    conditions = [
        {"field": "market", "values": ["5"]},
        {"field": "cash", "min": 20000, "max": 170000},
    ]
    payload = CreateSavedSearchPayload(
        resource=RESOURCE, name="test", filters=conditions
    )

    created = await service.create(user_id=1, payload=payload)

    # Stored verbatim — no coercion into an object wrapper.
    assert created.filters == conditions


@pytest.mark.parametrize(
    "filters",
    [
        {"bedrooms": 3},
        [{"field": "market", "values": ["5"]}],
        {},
        [],
    ],
)
def test_both_object_and_array_filter_shapes_validate(filters):
    payload = CreateSavedSearchPayload.model_validate(
        {"resource": RESOURCE, "name": "n", "filters": filters}
    )

    assert payload.filters == filters


@pytest.mark.parametrize("filters", ["a string", 42, True])
def test_scalar_filters_are_still_rejected(filters):
    with pytest.raises(ValidationError):
        CreateSavedSearchPayload.model_validate(
            {"resource": RESOURCE, "name": "n", "filters": filters}
        )


@pytest.mark.parametrize("name", ["   ", "\t\n", ""])
def test_whitespace_only_names_are_rejected(name):
    with pytest.raises(ValidationError):
        CreateSavedSearchPayload.model_validate(
            {"resource": RESOURCE, "name": name, "filters": {}}
        )


def test_names_are_stripped_so_padding_cannot_fake_a_distinct_search():
    payload = CreateSavedSearchPayload.model_validate(
        {"resource": RESOURCE, "name": "  Austin 3BR  ", "filters": {}}
    )

    assert payload.name == "Austin 3BR"


def test_patch_names_are_stripped_too():
    assert UpdateSavedSearchPayload(name=" renamed ").name == "renamed"


@pytest.mark.parametrize("resource", ["Bad Resource", "iron_bank..x", "", "a-b"])
def test_create_rejects_malformed_resource(resource):
    with pytest.raises(ValidationError):
        CreateSavedSearchPayload.model_validate(
            {"resource": resource, "name": "n", "filters": {}}
        )


@pytest.mark.asyncio
async def test_another_users_row_is_indistinguishable_from_a_missing_one():
    controller = SavedSearchController(
        SavedSearchService(StubRepository([_saved_search(1, user_id=2)]))
    )

    with pytest.raises(HTTPException) as excinfo:
        await controller.update_saved_search(
            saved_search_id=1,
            user_id=1,
            payload=UpdateSavedSearchPayload(name="hijacked"),
        )

    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_removes_only_an_owned_row():
    repository = StubRepository([_saved_search(1, user_id=1)])
    controller = SavedSearchController(SavedSearchService(repository))

    await controller.delete_saved_search(saved_search_id=1, user_id=1)

    assert repository.deleted == [1]


@pytest.mark.asyncio
async def test_list_failure_becomes_a_500():
    controller = SavedSearchController(
        SavedSearchService(StubRepository(error=RuntimeError("db down")))
    )

    with pytest.raises(HTTPException) as excinfo:
        await controller.list_saved_searches(user_id=1)

    assert excinfo.value.status_code == 500
