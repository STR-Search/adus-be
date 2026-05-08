from fastapi import HTTPException

from app.core.logger import logger
from app.markets.schemas.market import (
    MarketCreateSchema,
    MarketKeysMasterSchema,
    MarketUpdateSchema,
)
from app.markets.services.market_service import MarketService


class MarketController:
    def __init__(self, service: MarketService):
        self.service = service

    async def get_by_id(self, market_id: int) -> MarketKeysMasterSchema:
        try:
            market = await self.service.get_by_id(market_id)
            if market is None:
                raise HTTPException(status_code=404, detail=f"Market {market_id} not found")
            return market
        except HTTPException:
            raise
        except Exception as e:
            logger.error("market.get_by_id.error", market_id=market_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch market")

    async def get_by_market_slug(self, market_slug: str) -> MarketKeysMasterSchema:
        try:
            market = await self.service.get_by_market_slug(market_slug)
            if market is None:
                raise HTTPException(status_code=404, detail=f"Market '{market_slug}' not found")
            return market
        except HTTPException:
            raise
        except Exception as e:
            logger.error("market.get_by_market_slug.error", market_slug=market_slug, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch market")

    async def create(self, data: MarketCreateSchema) -> MarketKeysMasterSchema:
        try:
            return await self.service.create(data)
        except Exception as e:
            logger.error("market.create.error", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to create market")

    async def update(self, market_id: int, data: MarketUpdateSchema) -> MarketKeysMasterSchema:
        try:
            market = await self.service.update(market_id, data)
            if market is None:
                raise HTTPException(status_code=404, detail=f"Market {market_id} not found")
            return market
        except HTTPException:
            raise
        except Exception as e:
            logger.error("market.update.error", market_id=market_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to update market")

    async def delete(self, market_id: int) -> dict:
        try:
            deleted = await self.service.delete(market_id)
            if not deleted:
                raise HTTPException(status_code=404, detail=f"Market {market_id} not found")
            return {"detail": f"Market {market_id} deleted"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("market.delete.error", market_id=market_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to delete market")

    async def get_paginated(
        self,
        page: int,
        page_size: int,
        market_status: str | None = None,
        analyst_owner: str | None = None,
        search: str | None = None,
    ) -> dict:
        try:
            items, total, pages = await self.service.get_paginated(
                page=page,
                page_size=page_size,
                market_status=market_status,
                analyst_owner=analyst_owner,
                search=search,
            )
            return {"items": items, "total": total, "pages": pages, "page": page, "page_size": page_size}
        except Exception as e:
            logger.error("market.get_paginated.error", page=page, page_size=page_size, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch markets")
