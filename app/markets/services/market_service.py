from app.markets.models.market import MarketKeysMaster
from app.markets.models.realtor import Realtor
from app.markets.repositories.construction_repository import ConstructionAmenitiesRepository
from app.markets.repositories.market_repository import MarketRepository
from app.markets.repositories.realtor_repository import RealtorRepository
from app.markets.schemas.market import (
    AmenityRefSchema,
    MarketCreateSchema,
    MarketKeysMasterSchema,
    MarketSummarySchema,
    MarketUpdateSchema,
    RealtorRefSchema,
)
from app.users.schemas.user import UserSummary


class MarketService:
    def __init__(
        self,
        repository: MarketRepository,
        amenities_repository: ConstructionAmenitiesRepository,
        realtor_repository: RealtorRepository,
        user_repository=None,
    ):
        self.repository = repository
        self.amenities_repository = amenities_repository
        self.realtor_repository = realtor_repository
        # Optional: callers that only need market data (the underwriting jobs)
        # construct the service without it, and analyst_owner stays unresolved.
        self.user_repository = user_repository

    async def _get_amenity_name_map(self) -> dict[int, str | None]:
        records = await self.amenities_repository.get_all()
        return {record.id: record.amenity_name for record in records}

    async def _get_realtor_map(self) -> dict[int, RealtorRefSchema]:
        records = await self.realtor_repository.get_all()
        return {
            record.id: RealtorRefSchema(id=record.id, name=record.name, email=record.email)
            for record in records
        }

    async def _get_user_map(self) -> dict[int, UserSummary]:
        # No-op without a user repository; soft-deleted users are excluded by
        # the repository, so their ids simply fail to resolve.
        if self.user_repository is None:
            return {}
        records = await self.user_repository.get_all()
        return {record.id: UserSummary.model_validate(record) for record in records}

    async def _get_lookup_maps(
        self,
    ) -> tuple[dict[int, str | None], dict[int, RealtorRefSchema], dict[int, UserSummary]]:
        return (
            await self._get_amenity_name_map(),
            await self._get_realtor_map(),
            await self._get_user_map(),
        )

    async def _validate_amenity_ids(self, data: dict) -> None:
        ids: set[int] = set()
        for field in ("must_have_amenities", "nice_to_have_amenities"):
            ids.update(data.get(field) or [])
        if not ids:
            return
        amenity_name_map = await self._get_amenity_name_map()
        invalid = sorted(ids - amenity_name_map.keys())
        if invalid:
            raise ValueError(f"Unknown construction amenity ids: {invalid}")

    async def _validate_realtor_ids(self, data: dict) -> None:
        ids = set(data.get("realtor_ids") or [])
        if not ids:
            return
        realtor_map = await self._get_realtor_map()
        invalid = sorted(ids - realtor_map.keys())
        if invalid:
            raise ValueError(f"Unknown realtor ids: {invalid}")

    @staticmethod
    def _resolve_amenities(
        ids: list[int] | None, amenity_name_map: dict[int, str | None]
    ) -> list[AmenityRefSchema] | None:
        if ids is None:
            return None
        # IDs pointing at soft-deleted amenities are skipped.
        return [
            AmenityRefSchema(id=amenity_id, amenity_name=amenity_name_map[amenity_id])
            for amenity_id in ids
            if amenity_id in amenity_name_map
        ]

    @staticmethod
    def _resolve_realtors(
        ids: list[int] | None, realtor_map: dict[int, RealtorRefSchema]
    ) -> list[RealtorRefSchema] | None:
        if ids is None:
            return None
        # IDs pointing at soft-deleted realtors are skipped.
        return [realtor_map[realtor_id] for realtor_id in ids if realtor_id in realtor_map]

    def _to_schema(
        self,
        market: MarketKeysMaster,
        amenity_name_map: dict[int, str | None],
        realtor_map: dict[int, RealtorRefSchema],
        user_map: dict[int, UserSummary] | None = None,
    ) -> MarketKeysMasterSchema:
        return MarketKeysMasterSchema(
            id=market.id,
            market_slug=market.market_slug,
            market_name=market.market_name,
            market_name_current=market.market_name_current,
            market_status=market.market_status,
            analyst_owner_id=market.analyst_owner_id,
            analyst_owner=(user_map or {}).get(market.analyst_owner_id),
            market_notes=market.market_notes,
            map_config=market.map_config,
            filters=market.filters,
            must_have_amenities=self._resolve_amenities(market.must_have_amenities, amenity_name_map),
            nice_to_have_amenities=self._resolve_amenities(market.nice_to_have_amenities, amenity_name_map),
            realtors=self._resolve_realtors(market.realtor_ids, realtor_map),
            created_at=market.created_at,
            updated_at=market.updated_at,
        )

    async def get_by_id(self, market_id: int) -> MarketKeysMasterSchema | None:
        market = await self.repository.get_by_id(market_id)
        if market is None:
            return None
        return self._to_schema(market, *await self._get_lookup_maps())

    async def get_realtors_for_market(self, market_id: int) -> list[Realtor]:
        """Realtor rows attached to a market, in the market's realtor_ids order.

        Returns the ORM rows rather than RealtorRefSchema so callers get every
        column, including phone. Unknown or soft-deleted ids drop out; an
        unknown market yields an empty list.
        """
        market = await self.repository.get_by_id(market_id)
        realtor_ids = (market.realtor_ids or []) if market is not None else []
        if not realtor_ids:
            return []
        realtors = await self.realtor_repository.get_by_ids(set(realtor_ids))
        by_id = {realtor.id: realtor for realtor in realtors}
        return [by_id[realtor_id] for realtor_id in realtor_ids if realtor_id in by_id]

    async def get_by_market_slug(self, market_slug: str) -> MarketKeysMasterSchema | None:
        market = await self.repository.get_by_market_slug(market_slug)
        if market is None:
            return None
        return self._to_schema(market, *await self._get_lookup_maps())

    async def create(self, data: MarketCreateSchema) -> MarketKeysMasterSchema:
        payload = data.model_dump()
        await self._validate_amenity_ids(payload)
        await self._validate_realtor_ids(payload)
        market = await self.repository.create(payload)
        return self._to_schema(market, *await self._get_lookup_maps())

    async def update(self, market_id: int, data: MarketUpdateSchema) -> MarketKeysMasterSchema | None:
        payload = data.model_dump(exclude_unset=True)
        await self._validate_amenity_ids(payload)
        await self._validate_realtor_ids(payload)
        market = await self.repository.update(market_id, payload)
        if market is None:
            return None
        return self._to_schema(market, *await self._get_lookup_maps())

    async def get_all_summary(self) -> list[MarketSummarySchema]:
        items = await self.repository.get_all_summary()
        return [MarketSummarySchema.model_validate(item) for item in items]

    async def delete(self, market_id: int) -> bool:
        return await self.repository.delete(market_id)

    async def get_paginated(
        self,
        page: int,
        page_size: int,
        market_status: str | None = None,
        analyst_owner_id: int | None = None,
        search: str | None = None,
    ) -> tuple[list[MarketKeysMasterSchema], int, int]:
        items, total, pages = await self.repository.get_paginated(
            page=page,
            page_size=page_size,
            market_status=market_status,
            analyst_owner_id=analyst_owner_id,
            search=search,
        )
        amenity_name_map, realtor_map, user_map = await self._get_lookup_maps()
        return [
            self._to_schema(item, amenity_name_map, realtor_map, user_map)
            for item in items
        ], total, pages
