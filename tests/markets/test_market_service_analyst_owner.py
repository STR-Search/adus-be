"""Coverage for the analyst_owner hydration on markets.

market_keys_master stores analyst_owner_id (users.users.id); MarketService
resolves it to an ``analyst_owner`` UserSummary on the way out.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.markets.schemas.market import MarketUpdateSchema
from app.markets.services.market_service import MarketService
from app.users.schemas.user import UserSummary


def _market(market_id: int = 1, analyst_owner_id: int | None = 14, **overrides):
    base = dict(
        id=market_id,
        market_slug=f"market-{market_id}",
        market_name="Gatlinburg",
        market_name_current="Gatlinburg",
        market_status="active",
        analyst_owner_id=analyst_owner_id,
        market_notes=None,
        map_config=None,
        filters=None,
        must_have_amenities=None,
        nice_to_have_amenities=None,
        realtor_ids=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _user(user_id: int, first_name: str = "Taylor", last_name: str = "Jones"):
    return SimpleNamespace(
        id=user_id,
        clerk_id=f"user_{user_id}",
        email=f"u{user_id}@strsearch.com",
        first_name=first_name,
        last_name=last_name,
        is_deleted=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class FakeMarketRepository:
    def __init__(self, markets=None):
        self._markets = markets or []
        self.paginate_kwargs = None

    async def get_by_id(self, market_id: int):
        return next((m for m in self._markets if m.id == market_id), None)

    async def get_by_market_slug(self, market_slug: str):
        return next((m for m in self._markets if m.market_slug == market_slug), None)

    async def get_paginated(self, **kwargs):
        self.paginate_kwargs = kwargs
        return list(self._markets), len(self._markets), 1

    async def update(self, market_id: int, data: dict):
        market = await self.get_by_id(market_id)
        if market is None:
            return None
        for key, value in data.items():
            setattr(market, key, value)
        return market


class FakeEmptyRepository:
    """Stands in for the amenities and realtor repositories."""

    async def get_all(self):
        return []


class FakeUserRepository:
    def __init__(self, users=None):
        self._users = users or []
        self.get_all_calls = 0

    async def get_all(self):
        self.get_all_calls += 1
        # Mirrors the real repository: soft-deleted users never come back, so
        # their ids cannot resolve.
        return [u for u in self._users if u.is_deleted is not True]


def _service(markets=None, users=None, with_user_repository=True):
    market_repository = FakeMarketRepository(markets)
    user_repository = FakeUserRepository(users) if with_user_repository else None
    service = MarketService(
        market_repository,
        FakeEmptyRepository(),
        FakeEmptyRepository(),
        user_repository,
    )
    return service, market_repository, user_repository


@pytest.mark.asyncio
async def test_get_by_id_resolves_analyst_owner():
    service, _, _ = _service(
        markets=[_market(analyst_owner_id=14)],
        users=[_user(14)],
    )

    result = await service.get_by_id(1)

    assert result.analyst_owner_id == 14
    assert result.analyst_owner == UserSummary(
        id=14,
        email="u14@strsearch.com",
        first_name="Taylor",
        last_name="Jones",
    )


@pytest.mark.asyncio
async def test_null_analyst_owner_id_leaves_ref_none():
    service, _, _ = _service(
        markets=[_market(analyst_owner_id=None)],
        users=[_user(14)],
    )

    result = await service.get_by_id(1)

    assert result.analyst_owner_id is None
    assert result.analyst_owner is None


@pytest.mark.asyncio
async def test_unknown_user_id_keeps_raw_id_and_leaves_ref_none():
    service, _, _ = _service(markets=[_market(analyst_owner_id=999)], users=[_user(14)])

    result = await service.get_by_id(1)

    assert result.analyst_owner_id == 999
    assert result.analyst_owner is None


@pytest.mark.asyncio
async def test_soft_deleted_user_does_not_resolve():
    # The FK's ON DELETE SET NULL covers hard deletes; a soft-deleted user
    # keeps a live id that must not hydrate.
    deleted = _user(14)
    deleted.is_deleted = True
    service, _, _ = _service(markets=[_market(analyst_owner_id=14)], users=[deleted])

    result = await service.get_by_id(1)

    assert result.analyst_owner_id == 14
    assert result.analyst_owner is None


@pytest.mark.asyncio
async def test_without_user_repository_id_survives_but_ref_is_none():
    # The underwriting jobs build MarketService without a user repository.
    service, _, _ = _service(
        markets=[_market(analyst_owner_id=14)],
        with_user_repository=False,
    )

    result = await service.get_by_id(1)

    assert result.analyst_owner_id == 14
    assert result.analyst_owner is None


@pytest.mark.asyncio
async def test_get_by_market_slug_resolves_analyst_owner():
    service, _, _ = _service(markets=[_market(analyst_owner_id=14)], users=[_user(14)])

    result = await service.get_by_market_slug("market-1")

    assert result.analyst_owner.id == 14


@pytest.mark.asyncio
async def test_get_paginated_hydrates_page_in_one_user_lookup():
    markets = [
        _market(1, analyst_owner_id=14),
        _market(2, analyst_owner_id=3),
        _market(3, analyst_owner_id=None),
    ]
    users = [_user(14), _user(3, first_name="Carson", last_name="Whitley")]
    service, _, user_repository = _service(markets=markets, users=users)

    items, total, _ = await service.get_paginated(page=1, page_size=20)

    assert total == 3
    assert [i.analyst_owner_id for i in items] == [14, 3, None]
    assert [
        i.analyst_owner.first_name if i.analyst_owner else None for i in items
    ] == ["Taylor", "Carson", None]
    # One batched lookup for the whole page, not one per row.
    assert user_repository.get_all_calls == 1


@pytest.mark.asyncio
async def test_analyst_owner_id_filter_is_passed_to_repository():
    service, market_repository, _ = _service(markets=[], users=[])

    await service.get_paginated(page=1, page_size=20, analyst_owner_id=41)

    assert market_repository.paginate_kwargs["analyst_owner_id"] == 41


@pytest.mark.asyncio
async def test_update_writes_analyst_owner_id_and_returns_resolved_ref():
    service, _, _ = _service(
        markets=[_market(analyst_owner_id=None)],
        users=[_user(26, first_name="Jared", last_name="Schoen")],
    )

    result = await service.update(1, MarketUpdateSchema(analyst_owner_id=26))

    assert result.analyst_owner_id == 26
    assert result.analyst_owner.last_name == "Schoen"
