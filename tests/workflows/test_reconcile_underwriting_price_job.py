from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.workflows.reconcile_underwriting_price_job import (
    ReconcileUnderwritingPriceJob,
)


class FakeListingsService:
    def __init__(self, listing):
        self.listing = listing

    async def get_by_zpid(self, zpid):
        return self.listing


class FakeRepository:
    def __init__(self, underwriting):
        self.underwriting = underwriting

    async def get_by_zpid(self, zpid):
        return self.underwriting


class FakeBuilder:
    normalize_purchase_price = staticmethod(
        lambda value: None if value is None else Decimal(str(value))
    )

    def __init__(self, payload=None):
        self.payload = payload or object()
        self.received = None

    def build(self, *, underwriting, purchase_price):
        self.received = {
            "underwriting": underwriting,
            "purchase_price": purchase_price,
        }
        return self.payload


class FakeUpdateService:
    def __init__(self):
        self.received = None

    async def reconcile_purchase_price(self, underwriting_id, payload):
        self.received = {"underwriting_id": underwriting_id, "payload": payload}


def make_job(*, underwriting, listing, builder=None, update_service=None):
    return ReconcileUnderwritingPriceJob(
        listings_service=FakeListingsService(listing),
        underwriting_repository=FakeRepository(underwriting),
        payload_builder=builder or FakeBuilder(),
        update_service=update_service or FakeUpdateService(),
    )


@pytest.mark.asyncio
async def test_skips_when_underwriting_does_not_exist():
    result = await make_job(
        underwriting=None,
        listing=SimpleNamespace(unformatted_price="525000", price=None),
    ).run("1")

    assert result == {"zpid": "1", "status": "skipped_no_underwriting"}


@pytest.mark.parametrize(
    "listing",
    [None, SimpleNamespace(unformatted_price=None, price=None)],
)
@pytest.mark.asyncio
async def test_skips_when_zillow_purchase_price_is_missing(listing):
    result = await make_job(
        underwriting=SimpleNamespace(id=10, purchase_price=Decimal("485000")),
        listing=listing,
    ).run("1")

    assert result == {
        "zpid": "1",
        "status": "skipped_no_purchase_price",
        "underwriting_id": 10,
    }


@pytest.mark.asyncio
async def test_skips_when_purchase_price_is_unchanged():
    result = await make_job(
        underwriting=SimpleNamespace(id=10, purchase_price=Decimal("525000")),
        listing=SimpleNamespace(unformatted_price="525000", price=None),
    ).run("1")

    assert result == {
        "zpid": "1",
        "status": "skipped_same_price",
        "underwriting_id": 10,
    }


@pytest.mark.asyncio
async def test_reconciles_changed_purchase_price():
    underwriting = SimpleNamespace(id=10, purchase_price=Decimal("485000"))
    payload = object()
    builder = FakeBuilder(payload)
    update_service = FakeUpdateService()

    result = await make_job(
        underwriting=underwriting,
        listing=SimpleNamespace(unformatted_price="525000", price=None),
        builder=builder,
        update_service=update_service,
    ).run("1")

    assert result == {"zpid": "1", "status": "updated", "underwriting_id": 10}
    assert builder.received == {
        "underwriting": underwriting,
        "purchase_price": Decimal("525000"),
    }
    assert update_service.received == {
        "underwriting_id": 10,
        "payload": payload,
    }
