"""Seeding an exploratory market's opex from a lookalike active market.

The endpoint copies rows rather than linking to the source, so the guards are
what keep it honest: it refuses a non-exploratory target, refuses a target that
already holds rows (both opex tables carry a partial unique index that would
otherwise fail the insert mid-flight), and writes both tables under one commit
so a market never ends up with bedrooms rows but no size rows.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.markets.controllers.opex_controller import OpexSeedController
from app.markets.models.opex import OpexByBedrooms, OpexBySize
from app.markets.schemas.opex import OpexSeedRequestSchema
from app.markets.services.opex_service import (
    OpexSeedSameMarketError,
    OpexSeedService,
    OpexSeedSourceEmptyError,
    OpexSeedTargetAlreadySeededError,
    OpexSeedTargetNotExploratoryError,
)

SOURCE_ID = 1
TARGET_ID = 2


def _market(market_id: int, status: str | None):
    return SimpleNamespace(id=market_id, market_status=status, market_slug=f"m{market_id}")


def _bedrooms_row(record_id: int, bedrooms: int, market_id: int = SOURCE_ID):
    return OpexByBedrooms(
        id=record_id,
        market_id=market_id,
        bedrooms=bedrooms,
        cleaning_fee=100 + bedrooms,
        insurance_hoi=200 + bedrooms,
        pool_and_hot_tub=300 + bedrooms,
        deleted_at=None,
    )


def _size_row(record_id: int, sqft: int, market_id: int = SOURCE_ID):
    return OpexBySize(
        id=record_id,
        market_id=market_id,
        sqft=sqft,
        internet=75,
        utilities=sqft / 10,
        deleted_at=None,
    )


class StubSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class StubOpexRepository:
    """Holds rows per market and records what insert_all was handed."""

    def __init__(self, rows_by_market=None, *, raises=None):
        self._rows_by_market = rows_by_market or {}
        self._raises = raises
        self.inserted: list[dict] = []

    async def get_all_by_market(self, market_id):
        return list(self._rows_by_market.get(market_id, []))

    async def insert_all(self, rows):
        if self._raises is not None:
            raise self._raises
        self.inserted = rows
        return rows


class StubMarketRepository:
    def __init__(self, markets):
        self._markets = {m.id: m for m in markets}

    async def get_by_id(self, market_id):
        return self._markets.get(market_id)


def _service(
    *,
    target_status="exploratory",
    source_bedrooms=None,
    source_size=None,
    target_bedrooms=None,
    target_size=None,
    markets=None,
    bedrooms_raises=None,
    size_raises=None,
):
    session = StubSession()
    bedrooms_repo = StubOpexRepository(
        {
            SOURCE_ID: source_bedrooms if source_bedrooms is not None else [_bedrooms_row(10, 1)],
            TARGET_ID: target_bedrooms or [],
        },
        raises=bedrooms_raises,
    )
    size_repo = StubOpexRepository(
        {
            SOURCE_ID: source_size if source_size is not None else [_size_row(20, 500)],
            TARGET_ID: target_size or [],
        },
        raises=size_raises,
    )
    market_repo = StubMarketRepository(
        markets
        if markets is not None
        else [_market(SOURCE_ID, "active"), _market(TARGET_ID, target_status)]
    )
    service = OpexSeedService(session, bedrooms_repo, size_repo, market_repo)
    return service, session, bedrooms_repo, size_repo


@pytest.mark.asyncio
async def test_seeds_every_source_row_onto_the_target_and_commits_once():
    service, session, bedrooms_repo, size_repo = _service(
        source_bedrooms=[_bedrooms_row(10 + n, n) for n in range(1, 8)],
        source_size=[_size_row(20 + n, 500 * n) for n in range(1, 7)],
    )

    result = await service.seed_from_lookalike(TARGET_ID, SOURCE_ID)

    assert (result.bedrooms_created, result.size_created) == (7, 6)
    assert result.target_market_id == TARGET_ID
    assert session.committed is True
    assert {row["market_id"] for row in bedrooms_repo.inserted} == {TARGET_ID}
    assert {row["market_id"] for row in size_repo.inserted} == {TARGET_ID}


@pytest.mark.asyncio
async def test_copied_rows_carry_the_values_but_not_the_source_identity():
    """id and deleted_at are skipped so the insert gets a fresh sequence value;
    every other column rides across by name, including ones added later."""
    service, _, bedrooms_repo, _ = _service(source_bedrooms=[_bedrooms_row(10, 3)])

    await service.seed_from_lookalike(TARGET_ID, SOURCE_ID)

    row = bedrooms_repo.inserted[0]
    assert "id" not in row and "deleted_at" not in row
    assert row["bedrooms"] == 3
    assert row["cleaning_fee"] == 103
    assert row["insurance_hoi"] == 203
    # the column-generic clone is what makes a newly added column seed itself
    assert row["pool_and_hot_tub"] == 303


@pytest.mark.asyncio
async def test_row_count_is_not_assumed_to_be_seven_and_six():
    """Nothing in the schema pins those counts; whatever the source has is what
    gets copied."""
    service, _, _, _ = _service(
        source_bedrooms=[_bedrooms_row(10 + n, n) for n in range(1, 4)],
        source_size=[_size_row(20, 500)],
    )

    result = await service.seed_from_lookalike(TARGET_ID, SOURCE_ID)

    assert (result.bedrooms_created, result.size_created) == (3, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["active", None, "archived"])
async def test_a_non_exploratory_target_is_refused_before_anything_is_written(status):
    service, session, bedrooms_repo, _ = _service(target_status=status)

    with pytest.raises(OpexSeedTargetNotExploratoryError):
        await service.seed_from_lookalike(TARGET_ID, SOURCE_ID)

    assert bedrooms_repo.inserted == []
    assert session.committed is False


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["EXPLORATORY", "  Exploratory  "])
async def test_status_matching_survives_the_free_text_column(status):
    """market_status is varchar seeded verbatim from CSV, so the check has to
    normalize rather than coerce to the enum."""
    service, session, _, _ = _service(target_status=status)

    await service.seed_from_lookalike(TARGET_ID, SOURCE_ID)

    assert session.committed is True


@pytest.mark.asyncio
async def test_a_target_that_already_has_rows_is_refused_and_names_the_tables():
    service, session, _, _ = _service(
        target_bedrooms=[_bedrooms_row(50, 2, market_id=TARGET_ID)],
        target_size=[_size_row(60, 500, market_id=TARGET_ID)],
    )

    with pytest.raises(OpexSeedTargetAlreadySeededError) as excinfo:
        await service.seed_from_lookalike(TARGET_ID, SOURCE_ID)

    assert excinfo.value.tables == ["opex_by_bedrooms", "opex_by_size"]
    assert "go ahead and edit them" in str(excinfo.value)
    assert session.committed is False


@pytest.mark.asyncio
async def test_rows_in_only_one_target_table_still_refuse_the_whole_seed():
    """Seeding the empty half would leave a market half-copied from a source
    the other half never came from."""
    service, _, _, _ = _service(target_size=[_size_row(60, 500, market_id=TARGET_ID)])

    with pytest.raises(OpexSeedTargetAlreadySeededError) as excinfo:
        await service.seed_from_lookalike(TARGET_ID, SOURCE_ID)

    assert excinfo.value.tables == ["opex_by_size"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"source_bedrooms": [], "source_size": []}, ["opex_by_bedrooms", "opex_by_size"]),
        ({"source_bedrooms": []}, ["opex_by_bedrooms"]),
        ({"source_size": []}, ["opex_by_size"]),
    ],
)
async def test_a_source_missing_either_table_is_refused(kwargs, expected):
    service, session, _, _ = _service(**kwargs)

    with pytest.raises(OpexSeedSourceEmptyError) as excinfo:
        await service.seed_from_lookalike(TARGET_ID, SOURCE_ID)

    assert excinfo.value.empty_tables == expected
    assert session.committed is False


@pytest.mark.asyncio
async def test_seeding_a_market_from_itself_is_refused():
    service, _, _, _ = _service()

    with pytest.raises(OpexSeedSameMarketError):
        await service.seed_from_lookalike(TARGET_ID, TARGET_ID)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [SOURCE_ID, TARGET_ID])
async def test_a_missing_market_on_either_side_raises_value_error(missing):
    present = TARGET_ID if missing == SOURCE_ID else SOURCE_ID
    status = "exploratory" if present == TARGET_ID else "active"
    service, _, _, _ = _service(markets=[_market(present, status)])

    with pytest.raises(ValueError, match=str(missing)):
        await service.seed_from_lookalike(TARGET_ID, SOURCE_ID)


@pytest.mark.asyncio
async def test_a_failure_on_the_second_table_rolls_back_the_first():
    """The two inserts are one transaction; without the rollback the bedrooms
    rows would survive a size failure and poison the retry."""
    service, session, _, _ = _service(size_raises=RuntimeError("unique violation"))

    with pytest.raises(RuntimeError):
        await service.seed_from_lookalike(TARGET_ID, SOURCE_ID)

    assert session.rolled_back is True
    assert session.committed is False


@pytest.mark.asyncio
async def test_controller_turns_an_already_seeded_target_into_a_409():
    service, _, _, _ = _service(
        target_bedrooms=[_bedrooms_row(50, 2, market_id=TARGET_ID)]
    )

    with pytest.raises(HTTPException) as excinfo:
        await OpexSeedController(service).seed_from_lookalike(
            TARGET_ID, OpexSeedRequestSchema(source_market_id=SOURCE_ID)
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["tables"] == ["opex_by_bedrooms"]


@pytest.mark.asyncio
async def test_controller_turns_a_non_exploratory_target_into_a_409():
    service, _, _, _ = _service(target_status="active")

    with pytest.raises(HTTPException) as excinfo:
        await OpexSeedController(service).seed_from_lookalike(
            TARGET_ID, OpexSeedRequestSchema(source_market_id=SOURCE_ID)
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["market_status"] == "active"


@pytest.mark.asyncio
async def test_controller_turns_an_empty_source_into_a_400():
    service, _, _, _ = _service(source_size=[])

    with pytest.raises(HTTPException) as excinfo:
        await OpexSeedController(service).seed_from_lookalike(
            TARGET_ID, OpexSeedRequestSchema(source_market_id=SOURCE_ID)
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail["empty_tables"] == ["opex_by_size"]


@pytest.mark.asyncio
async def test_controller_turns_a_missing_market_into_a_404():
    service, _, _, _ = _service(markets=[_market(TARGET_ID, "exploratory")])

    with pytest.raises(HTTPException) as excinfo:
        await OpexSeedController(service).seed_from_lookalike(
            TARGET_ID, OpexSeedRequestSchema(source_market_id=SOURCE_ID)
        )

    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_controller_returns_the_counts_on_success():
    service, _, _, _ = _service(
        source_bedrooms=[_bedrooms_row(10 + n, n) for n in range(1, 8)],
        source_size=[_size_row(20 + n, 500 * n) for n in range(1, 7)],
    )

    result = await OpexSeedController(service).seed_from_lookalike(
        TARGET_ID, OpexSeedRequestSchema(source_market_id=SOURCE_ID)
    )

    assert (result.bedrooms_created, result.size_created) == (7, 6)
    assert result.source_market_id == SOURCE_ID
