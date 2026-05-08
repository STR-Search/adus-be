from app.markets.models.opex import OpexByBedrooms, OpexBySize
from app.markets.repositories.market_repository import MarketRepository
from app.markets.repositories.opex_repository import OpexByBedroomsRepository, OpexBySizeRepository
from app.markets.schemas.opex import (
    OpexByBedroomsCreateSchema,
    OpexByBedroomsSchema,
    OpexByBedroomsUpdateSchema,
    OpexBySizeCreateSchema,
    OpexBySizeSchema,
    OpexBySizeUpdateSchema,
)


class OpexByBedroomsService:
    def __init__(self, repository: OpexByBedroomsRepository, market_repo: MarketRepository):
        self.repository = repository
        self.market_repo = market_repo

    async def _resolve_market_id(self, market_id: int | None, market_slug: str | None) -> int | None:
        if market_slug is not None:
            market = await self.market_repo.get_by_market_slug(market_slug)
            if market is None:
                raise ValueError(f"market_slug '{market_slug}' not found")
            return market.id
        return market_id

    async def _with_slug(self, record: OpexByBedrooms, slug_map: dict[int, str]) -> OpexByBedroomsSchema:
        schema = OpexByBedroomsSchema.model_validate(record)
        if record.market_id is not None:
            schema = schema.model_copy(update={"market_slug": slug_map.get(record.market_id)})
        return schema

    async def get_by_id(self, record_id: int) -> OpexByBedroomsSchema | None:
        record = await self.repository.get_by_id(record_id)
        if record is None:
            return None
        slug_map = await self.market_repo.get_slug_map(
            {record.market_id} if record.market_id is not None else set()
        )
        return await self._with_slug(record, slug_map)

    async def get_by_market_and_bedrooms(
        self,
        bedrooms: int,
        market_id: int | None = None,
        market_slug: str | None = None,
    ) -> OpexByBedroomsSchema | None:
        resolved_market_id = await self._resolve_market_id(market_id, market_slug)
        if resolved_market_id is None:
            return None
        record = await self.repository.get_by_market_and_bedrooms(resolved_market_id, bedrooms)
        if record is None:
            return None
        slug_map = await self.market_repo.get_slug_map({resolved_market_id})
        return await self._with_slug(record, slug_map)

    async def get_paginated(
        self,
        page: int,
        page_size: int,
        market_id: int | None = None,
        market_slug: str | None = None,
        bedrooms: int | None = None,
    ) -> tuple[list[OpexByBedroomsSchema], int, int]:
        resolved_market_id = await self._resolve_market_id(market_id, market_slug)
        items, total, pages = await self.repository.get_paginated(
            page=page,
            page_size=page_size,
            market_id=resolved_market_id,
            bedrooms=bedrooms,
        )
        slug_map = await self.market_repo.get_slug_map(
            {item.market_id for item in items if item.market_id is not None}
        )
        return [await self._with_slug(item, slug_map) for item in items], total, pages

    async def create(self, data: OpexByBedroomsCreateSchema) -> OpexByBedroomsSchema:
        market = await self._resolve_market_id(data.market_id, data.market_slug)
        payload = data.model_dump(exclude={"market_id", "market_slug"})
        payload["market_id"] = market
        record = await self.repository.create(payload)
        slug_map = await self.market_repo.get_slug_map(
            {record.market_id} if record.market_id is not None else set()
        )
        return await self._with_slug(record, slug_map)

    async def update(self, record_id: int, data: OpexByBedroomsUpdateSchema) -> OpexByBedroomsSchema | None:
        market = await self._resolve_market_id(data.market_id, data.market_slug)
        payload = data.model_dump(exclude={"market_id", "market_slug"}, exclude_unset=True)
        if market is not None or data.market_id is not None or data.market_slug is not None:
            payload["market_id"] = market
        record = await self.repository.update(record_id, payload)
        if record is None:
            return None
        slug_map = await self.market_repo.get_slug_map(
            {record.market_id} if record.market_id is not None else set()
        )
        return await self._with_slug(record, slug_map)

    async def delete(self, record_id: int) -> bool:
        return await self.repository.delete(record_id)


class OpexBySizeService:
    def __init__(self, repository: OpexBySizeRepository, market_repo: MarketRepository):
        self.repository = repository
        self.market_repo = market_repo

    async def _resolve_market_id(self, market_id: int | None, market_slug: str | None) -> int | None:
        if market_slug is not None:
            market = await self.market_repo.get_by_market_slug(market_slug)
            if market is None:
                raise ValueError(f"market_slug '{market_slug}' not found")
            return market.id
        return market_id

    async def _with_slug(self, record: OpexBySize, slug_map: dict[int, str]) -> OpexBySizeSchema:
        schema = OpexBySizeSchema.model_validate(record)
        if record.market_id is not None:
            schema = schema.model_copy(update={"market_slug": slug_map.get(record.market_id)})
        return schema

    async def get_by_id(self, record_id: int) -> OpexBySizeSchema | None:
        record = await self.repository.get_by_id(record_id)
        if record is None:
            return None
        slug_map = await self.market_repo.get_slug_map(
            {record.market_id} if record.market_id is not None else set()
        )
        return await self._with_slug(record, slug_map)

    async def get_by_market_and_sqft(
        self,
        sqft: int,
        market_id: int | None = None,
        market_slug: str | None = None,
    ) -> OpexBySizeSchema | None:
        resolved_market_id = await self._resolve_market_id(market_id, market_slug)
        if resolved_market_id is None:
            return None
        record = await self.repository.get_by_market_and_sqft(resolved_market_id, sqft)
        if record is None:
            return None
        slug_map = await self.market_repo.get_slug_map({resolved_market_id})
        return await self._with_slug(record, slug_map)

    async def get_paginated(
        self,
        page: int,
        page_size: int,
        market_id: int | None = None,
        market_slug: str | None = None,
        sqft: int | None = None,
    ) -> tuple[list[OpexBySizeSchema], int, int]:
        resolved_market_id = await self._resolve_market_id(market_id, market_slug)
        items, total, pages = await self.repository.get_paginated(
            page=page,
            page_size=page_size,
            market_id=resolved_market_id,
            sqft=sqft,
        )
        slug_map = await self.market_repo.get_slug_map(
            {item.market_id for item in items if item.market_id is not None}
        )
        return [await self._with_slug(item, slug_map) for item in items], total, pages

    async def create(self, data: OpexBySizeCreateSchema) -> OpexBySizeSchema:
        market = await self._resolve_market_id(data.market_id, data.market_slug)
        payload = data.model_dump(exclude={"market_id", "market_slug"})
        payload["market_id"] = market
        record = await self.repository.create(payload)
        slug_map = await self.market_repo.get_slug_map(
            {record.market_id} if record.market_id is not None else set()
        )
        return await self._with_slug(record, slug_map)

    async def update(self, record_id: int, data: OpexBySizeUpdateSchema) -> OpexBySizeSchema | None:
        market = await self._resolve_market_id(data.market_id, data.market_slug)
        payload = data.model_dump(exclude={"market_id", "market_slug"}, exclude_unset=True)
        if market is not None or data.market_id is not None or data.market_slug is not None:
            payload["market_id"] = market
        record = await self.repository.update(record_id, payload)
        if record is None:
            return None
        slug_map = await self.market_repo.get_slug_map(
            {record.market_id} if record.market_id is not None else set()
        )
        return await self._with_slug(record, slug_map)

    async def delete(self, record_id: int) -> bool:
        return await self.repository.delete(record_id)
