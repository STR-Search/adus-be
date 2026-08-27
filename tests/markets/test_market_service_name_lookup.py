"""Coverage for the lean market-name lookup.

``get_market_name_current`` exists so callers that only need to *name* a market
— the listing/market mismatch 409 on the create-from-URL flow — don't pay for
the amenity, realtor and user maps that ``get_by_id`` builds.
"""

from types import SimpleNamespace

import pytest

from app.markets.services.market_service import MarketService


class FakeMarketRepository:
    def __init__(self, market=None):
        self.market = market
        self.requested_id = None

    async def get_by_id(self, market_id: int):
        self.requested_id = market_id
        return self.market


class ExplodingRepository:
    """Any lookup map built here means the lean path was not taken."""

    async def get_all(self):
        raise AssertionError("lookup maps must not be built to name a market")


def _service(market):
    return MarketService(
        FakeMarketRepository(market),
        ExplodingRepository(),
        ExplodingRepository(),
        user_repository=ExplodingRepository(),
    )


@pytest.mark.asyncio
async def test_returns_the_current_name():
    service = _service(
        SimpleNamespace(market_name_current="Austin, TX", market_name="Austin")
    )

    assert await service.get_market_name_current(3) == "Austin, TX"


@pytest.mark.asyncio
async def test_falls_back_to_market_name_when_current_is_null():
    """market_name_current is nullable, so it can't be the only source."""
    service = _service(
        SimpleNamespace(market_name_current=None, market_name="Austin")
    )

    assert await service.get_market_name_current(3) == "Austin"


@pytest.mark.asyncio
async def test_returns_none_for_an_unknown_or_soft_deleted_market():
    """The repository filters deleted_at IS NOT NULL, so both look the same."""
    service = _service(None)

    assert await service.get_market_name_current(3) is None


@pytest.mark.asyncio
async def test_returns_none_when_neither_name_is_set():
    service = _service(SimpleNamespace(market_name_current=None, market_name=None))

    assert await service.get_market_name_current(3) is None


@pytest.mark.asyncio
async def test_queries_the_requested_market():
    repository = FakeMarketRepository(
        SimpleNamespace(market_name_current="Austin, TX", market_name=None)
    )
    service = MarketService(repository, ExplodingRepository(), ExplodingRepository())

    await service.get_market_name_current(7)

    assert repository.requested_id == 7
