from app.markets.repositories.market_repository import MarketRepository
from app.markets.schemas.market import (
    MarketCreateSchema,
    MarketKeysMasterSchema,
    MarketUpdateSchema,
)


class MarketService:
    def __init__(self, repository: MarketRepository):
        self.repository = repository

    async def get_by_id(self, market_id: int) -> MarketKeysMasterSchema | None:
        market = await self.repository.get_by_id(market_id)
        if market is None:
            return None
        return MarketKeysMasterSchema.model_validate(market)

    async def get_by_market_slug(self, market_slug: str) -> MarketKeysMasterSchema | None:
        market = await self.repository.get_by_market_slug(market_slug)
        if market is None:
            return None
        return MarketKeysMasterSchema.model_validate(market)

    async def create(self, data: MarketCreateSchema) -> MarketKeysMasterSchema:
        market = await self.repository.create(data.model_dump())
        return MarketKeysMasterSchema.model_validate(market)

    async def update(self, market_id: int, data: MarketUpdateSchema) -> MarketKeysMasterSchema | None:
        market = await self.repository.update(market_id, data.model_dump(exclude_unset=True))
        if market is None:
            return None
        return MarketKeysMasterSchema.model_validate(market)

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
        return [MarketKeysMasterSchema.model_validate(item) for item in items], total, pages
