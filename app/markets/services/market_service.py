from app.markets.models.market import MarketKeysMaster
from app.markets.repositories.construction_repository import ConstructionAmenitiesRepository
from app.markets.repositories.market_repository import MarketRepository
from app.markets.schemas.market import (
    AmenityRefSchema,
    MarketCreateSchema,
    MarketKeysMasterSchema,
    MarketSummarySchema,
    MarketUpdateSchema,
)


class MarketService:
    def __init__(self, repository: MarketRepository, amenities_repository: ConstructionAmenitiesRepository):
        self.repository = repository
        self.amenities_repository = amenities_repository

    async def _get_amenity_name_map(self) -> dict[int, str | None]:
        records = await self.amenities_repository.get_all()
        return {record.id: record.amenity_name for record in records}

    async def _validate_amenity_ids(self, data: dict) -> None:
        ids: set[int] = set()
        for field in ("must_have_amenities", "nice_to_have_amenities"):
            ids.update(data.get(field) or [])
        if not ids:
            return
        name_map = await self._get_amenity_name_map()
        invalid = sorted(ids - name_map.keys())
        if invalid:
            raise ValueError(f"Unknown construction amenity ids: {invalid}")

    @staticmethod
    def _resolve_amenities(
        ids: list[int] | None, name_map: dict[int, str | None]
    ) -> list[AmenityRefSchema] | None:
        if ids is None:
            return None
        # IDs pointing at soft-deleted amenities are skipped.
        return [
            AmenityRefSchema(id=amenity_id, amenity_name=name_map[amenity_id])
            for amenity_id in ids
            if amenity_id in name_map
        ]

    def _to_schema(
        self, market: MarketKeysMaster, name_map: dict[int, str | None]
    ) -> MarketKeysMasterSchema:
        return MarketKeysMasterSchema(
            id=market.id,
            market_slug=market.market_slug,
            market_name=market.market_name,
            market_name_current=market.market_name_current,
            market_status=market.market_status,
            analyst_owner=market.analyst_owner,
            map_config=market.map_config,
            filters=market.filters,
            must_have_amenities=self._resolve_amenities(market.must_have_amenities, name_map),
            nice_to_have_amenities=self._resolve_amenities(market.nice_to_have_amenities, name_map),
            created_at=market.created_at,
            updated_at=market.updated_at,
        )

    async def get_by_id(self, market_id: int) -> MarketKeysMasterSchema | None:
        market = await self.repository.get_by_id(market_id)
        if market is None:
            return None
        return self._to_schema(market, await self._get_amenity_name_map())

    async def get_by_market_slug(self, market_slug: str) -> MarketKeysMasterSchema | None:
        market = await self.repository.get_by_market_slug(market_slug)
        if market is None:
            return None
        return self._to_schema(market, await self._get_amenity_name_map())

    async def create(self, data: MarketCreateSchema) -> MarketKeysMasterSchema:
        payload = data.model_dump()
        await self._validate_amenity_ids(payload)
        market = await self.repository.create(payload)
        return self._to_schema(market, await self._get_amenity_name_map())

    async def update(self, market_id: int, data: MarketUpdateSchema) -> MarketKeysMasterSchema | None:
        payload = data.model_dump(exclude_unset=True)
        await self._validate_amenity_ids(payload)
        market = await self.repository.update(market_id, payload)
        if market is None:
            return None
        return self._to_schema(market, await self._get_amenity_name_map())

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
        analyst_owner: str | None = None,
        search: str | None = None,
    ) -> tuple[list[MarketKeysMasterSchema], int, int]:
        items, total, pages = await self.repository.get_paginated(
            page=page,
            page_size=page_size,
            market_status=market_status,
            analyst_owner=analyst_owner,
            search=search,
        )
        name_map = await self._get_amenity_name_map()
        return [self._to_schema(item, name_map) for item in items], total, pages
