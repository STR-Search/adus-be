from datetime import datetime

import pytest

from app.airbnb_public.models.cleaned_data import CleanedData
from app.airbnb_public.schemas.cleaned_data import CleanedDataSchema
from app.airbnb_public.services.cleaned_data_service import CleanedDataService


def test_cleaned_data_model_maps_public_cleaned_data_table() -> None:
    assert CleanedData.__tablename__ == "cleaned_data"
    assert CleanedData.__table__.schema == "public"
    assert CleanedData.__table__.primary_key.columns.keys() == ["id"]
    assert CleanedData.__table__.c.property_id.type.length == 100
    assert CleanedData.__table__.c.key_market.type.length == 255
    assert CleanedData.__table__.c.zipcode.type.length == 20
    assert CleanedData.__table__.c.property_type.nullable is False


def test_cleaned_data_schema_validates_from_model() -> None:
    row = CleanedData(
        id=1,
        market_run_execution_id=10,
        property_id="abc-123",
        listing_title="Cabin near downtown",
        bedrooms=3,
        baths=2.5,
        has_hot_tub=True,
        data_date=datetime(2026, 6, 1),
        property_type="single-family home",
    )

    data = CleanedDataSchema.model_validate(row)

    assert data.id == 1
    assert data.market_run_execution_id == 10
    assert data.property_id == "abc-123"
    assert data.listing_title == "Cabin near downtown"
    assert data.bedrooms == 3
    assert data.baths == 2.5
    assert data.has_hot_tub is True
    assert data.property_type == "single-family home"


class StubCleanedDataRepository:
    def __init__(self, row: CleanedData | None):
        self.row = row
        self.seen_id: int | None = None

    async def get_by_id(self, cleaned_data_id: int) -> CleanedData | None:
        self.seen_id = cleaned_data_id
        return self.row


@pytest.mark.asyncio
async def test_cleaned_data_service_returns_schema_by_id() -> None:
    row = CleanedData(
        id=2,
        market_run_execution_id=11,
        property_type="single-family home",
    )
    repository = StubCleanedDataRepository(row)
    service = CleanedDataService(repository)

    data = await service.get_by_id(2)

    assert repository.seen_id == 2
    assert data == CleanedDataSchema.model_validate(row)


@pytest.mark.asyncio
async def test_cleaned_data_service_returns_none_when_missing() -> None:
    repository = StubCleanedDataRepository(None)
    service = CleanedDataService(repository)

    data = await service.get_by_id(99)

    assert repository.seen_id == 99
    assert data is None
