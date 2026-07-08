from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.markets.controllers.construction_controller import (
    ConstructionAmenitiesController,
    ConstructionRemodelingController,
)
from app.markets.controllers.market_controller import MarketController
from app.markets.controllers.opex_controller import OpexByBedroomsController, OpexBySizeController
from app.markets.controllers.str_cribs_controller import StrCribsFeeDetailsController
from app.markets.repositories.construction_repository import (
    ConstructionAmenitiesRepository,
    ConstructionRemodelingRepository,
)
from app.markets.repositories.market_repository import MarketRepository
from app.markets.repositories.opex_repository import OpexByBedroomsRepository, OpexBySizeRepository
from app.markets.repositories.str_cribs_repository import StrCribsFeeDetailsRepository
from app.markets.schemas.construction import (
    ConstructionCostsAmenitiesCreateSchema,
    ConstructionCostsAmenitiesUpdateSchema,
    ConstructionCostsRemodelingCreateSchema,
    ConstructionCostsRemodelingUpdateSchema,
)
from app.markets.schemas.market import MarketCreateSchema, MarketUpdateSchema
from app.markets.schemas.opex import (
    OpexByBedroomsCreateSchema,
    OpexByBedroomsUpdateSchema,
    OpexBySizeCreateSchema,
    OpexBySizeUpdateSchema,
)
from app.markets.schemas.str_cribs import (
    StrCribsFeeDetailsCreateSchema,
    StrCribsFeeDetailsUpdateSchema,
)
from app.markets.services.construction_service import ConstructionAmenitiesService, ConstructionRemodelingService
from app.markets.services.market_service import MarketService
from app.markets.services.opex_service import OpexByBedroomsService, OpexBySizeService
from app.markets.services.str_cribs_service import StrCribsFeeDetailsService

router = APIRouter()


# --- Dependency factories ---

def get_market_controller(db: AsyncSession = Depends(get_db)) -> MarketController:
    return MarketController(MarketService(MarketRepository(db)))


def get_amenities_controller(db: AsyncSession = Depends(get_db)) -> ConstructionAmenitiesController:
    return ConstructionAmenitiesController(ConstructionAmenitiesService(ConstructionAmenitiesRepository(db)))


def get_remodeling_controller(db: AsyncSession = Depends(get_db)) -> ConstructionRemodelingController:
    return ConstructionRemodelingController(ConstructionRemodelingService(ConstructionRemodelingRepository(db)))


def get_bedrooms_controller(db: AsyncSession = Depends(get_db)) -> OpexByBedroomsController:
    market_repo = MarketRepository(db)
    return OpexByBedroomsController(OpexByBedroomsService(OpexByBedroomsRepository(db), market_repo))


def get_size_controller(db: AsyncSession = Depends(get_db)) -> OpexBySizeController:
    market_repo = MarketRepository(db)
    return OpexBySizeController(OpexBySizeService(OpexBySizeRepository(db), market_repo))


def get_str_cribs_controller(db: AsyncSession = Depends(get_db)) -> StrCribsFeeDetailsController:
    return StrCribsFeeDetailsController(StrCribsFeeDetailsService(StrCribsFeeDetailsRepository(db)))


# --- Health ---

@router.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


# --- Markets ---

@router.get("/markets/", tags=["markets"])
async def get_markets_paginated(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    market_status: str | None = Query(None),
    analyst_owner: str | None = Query(None),
    search: str | None = Query(None),
    controller: MarketController = Depends(get_market_controller),
):
    return await controller.get_paginated(
        page=page,
        page_size=page_size,
        market_status=market_status,
        analyst_owner=analyst_owner,
        search=search,
    )


@router.get("/markets/all", tags=["markets"])
async def get_all_markets(
    controller: MarketController = Depends(get_market_controller),
):
    return await controller.get_all_summary()


@router.get("/markets/slug/{market_slug}", tags=["markets"])
async def get_market_by_slug(
    market_slug: str,
    controller: MarketController = Depends(get_market_controller),
):
    return await controller.get_by_market_slug(market_slug)


@router.get("/markets/{market_id}", tags=["markets"])
async def get_market_by_id(
    market_id: int,
    controller: MarketController = Depends(get_market_controller),
):
    return await controller.get_by_id(market_id)


@router.post("/markets/", status_code=201, tags=["markets"])
async def create_market(
    data: MarketCreateSchema,
    controller: MarketController = Depends(get_market_controller),
):
    return await controller.create(data)


@router.patch("/markets/{market_id}", tags=["markets"])
async def update_market(
    market_id: int,
    data: MarketUpdateSchema,
    controller: MarketController = Depends(get_market_controller),
):
    return await controller.update(market_id, data)


@router.delete("/markets/{market_id}", tags=["markets"])
async def delete_market(
    market_id: int,
    controller: MarketController = Depends(get_market_controller),
):
    return await controller.delete(market_id)


# --- Construction: Amenities ---

@router.get("/construction/amenities/", tags=["construction"])
async def get_all_amenities(
    location: str | None = Query(None),
    search: str | None = Query(None),
    controller: ConstructionAmenitiesController = Depends(get_amenities_controller),
):
    return await controller.get_all(location=location, search=search)


@router.get("/construction/amenities/{record_id}", tags=["construction"])
async def get_amenity_by_id(
    record_id: int,
    controller: ConstructionAmenitiesController = Depends(get_amenities_controller),
):
    return await controller.get_by_id(record_id)


@router.post("/construction/amenities/", status_code=201, tags=["construction"])
async def create_amenity(
    data: ConstructionCostsAmenitiesCreateSchema,
    controller: ConstructionAmenitiesController = Depends(get_amenities_controller),
):
    return await controller.create(data)


@router.patch("/construction/amenities/{record_id}", tags=["construction"])
async def update_amenity(
    record_id: int,
    data: ConstructionCostsAmenitiesUpdateSchema,
    controller: ConstructionAmenitiesController = Depends(get_amenities_controller),
):
    return await controller.update(record_id, data)


@router.delete("/construction/amenities/{record_id}", tags=["construction"])
async def delete_amenity(
    record_id: int,
    controller: ConstructionAmenitiesController = Depends(get_amenities_controller),
):
    return await controller.delete(record_id)


# --- Construction: Remodeling ---

@router.get("/construction/remodeling/", tags=["construction"])
async def get_all_remodeling(
    location: str | None = Query(None),
    search: str | None = Query(None),
    controller: ConstructionRemodelingController = Depends(get_remodeling_controller),
):
    return await controller.get_all(location=location, search=search)


@router.get("/construction/remodeling/{record_id}", tags=["construction"])
async def get_remodeling_by_id(
    record_id: int,
    controller: ConstructionRemodelingController = Depends(get_remodeling_controller),
):
    return await controller.get_by_id(record_id)


@router.post("/construction/remodeling/", status_code=201, tags=["construction"])
async def create_remodeling(
    data: ConstructionCostsRemodelingCreateSchema,
    controller: ConstructionRemodelingController = Depends(get_remodeling_controller),
):
    return await controller.create(data)


@router.patch("/construction/remodeling/{record_id}", tags=["construction"])
async def update_remodeling(
    record_id: int,
    data: ConstructionCostsRemodelingUpdateSchema,
    controller: ConstructionRemodelingController = Depends(get_remodeling_controller),
):
    return await controller.update(record_id, data)


@router.delete("/construction/remodeling/{record_id}", tags=["construction"])
async def delete_remodeling(
    record_id: int,
    controller: ConstructionRemodelingController = Depends(get_remodeling_controller),
):
    return await controller.delete(record_id)


# --- Opex: By Bedrooms ---

@router.get("/opex/bedrooms/", tags=["opex"])
async def get_bedrooms_paginated(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    market_id: int | None = Query(None),
    market_slug: str | None = Query(None),
    bedrooms: int | None = Query(None),
    controller: OpexByBedroomsController = Depends(get_bedrooms_controller),
):
    return await controller.get_paginated(
        page=page,
        page_size=page_size,
        market_id=market_id,
        market_slug=market_slug,
        bedrooms=bedrooms,
    )


@router.get("/opex/bedrooms/{record_id}", tags=["opex"])
async def get_bedrooms_by_id(
    record_id: int,
    controller: OpexByBedroomsController = Depends(get_bedrooms_controller),
):
    return await controller.get_by_id(record_id)


@router.post("/opex/bedrooms/", status_code=201, tags=["opex"])
async def create_bedrooms(
    data: OpexByBedroomsCreateSchema,
    controller: OpexByBedroomsController = Depends(get_bedrooms_controller),
):
    return await controller.create(data)


@router.patch("/opex/bedrooms/{record_id}", tags=["opex"])
async def update_bedrooms(
    record_id: int,
    data: OpexByBedroomsUpdateSchema,
    controller: OpexByBedroomsController = Depends(get_bedrooms_controller),
):
    return await controller.update(record_id, data)


@router.delete("/opex/bedrooms/{record_id}", tags=["opex"])
async def delete_bedrooms(
    record_id: int,
    controller: OpexByBedroomsController = Depends(get_bedrooms_controller),
):
    return await controller.delete(record_id)


# --- Opex: By Size ---

@router.get("/opex/size/", tags=["opex"])
async def get_size_paginated(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    market_id: int | None = Query(None),
    market_slug: str | None = Query(None),
    sqft: int | None = Query(None),
    controller: OpexBySizeController = Depends(get_size_controller),
):
    return await controller.get_paginated(
        page=page,
        page_size=page_size,
        market_id=market_id,
        market_slug=market_slug,
        sqft=sqft,
    )


@router.get("/opex/size/{record_id}", tags=["opex"])
async def get_size_by_id(
    record_id: int,
    controller: OpexBySizeController = Depends(get_size_controller),
):
    return await controller.get_by_id(record_id)


@router.post("/opex/size/", status_code=201, tags=["opex"])
async def create_size(
    data: OpexBySizeCreateSchema,
    controller: OpexBySizeController = Depends(get_size_controller),
):
    return await controller.create(data)


@router.patch("/opex/size/{record_id}", tags=["opex"])
async def update_size(
    record_id: int,
    data: OpexBySizeUpdateSchema,
    controller: OpexBySizeController = Depends(get_size_controller),
):
    return await controller.update(record_id, data)


@router.delete("/opex/size/{record_id}", tags=["opex"])
async def delete_size(
    record_id: int,
    controller: OpexBySizeController = Depends(get_size_controller),
):
    return await controller.delete(record_id)


# --- STR Cribs: Fee Details ---

@router.get("/str-cribs/fee-details/", tags=["str-cribs"])
async def get_str_cribs_fee_details(
    controller: StrCribsFeeDetailsController = Depends(get_str_cribs_controller),
):
    return await controller.get_all()


@router.get("/str-cribs/fee-details/{record_id}", tags=["str-cribs"])
async def get_str_cribs_fee_detail_by_id(
    record_id: int,
    controller: StrCribsFeeDetailsController = Depends(get_str_cribs_controller),
):
    return await controller.get_by_id(record_id)


@router.post("/str-cribs/fee-details/", status_code=201, tags=["str-cribs"])
async def create_str_cribs_fee_detail(
    data: StrCribsFeeDetailsCreateSchema,
    controller: StrCribsFeeDetailsController = Depends(get_str_cribs_controller),
):
    return await controller.create(data)


@router.patch("/str-cribs/fee-details/{record_id}", tags=["str-cribs"])
async def update_str_cribs_fee_detail(
    record_id: int,
    data: StrCribsFeeDetailsUpdateSchema,
    controller: StrCribsFeeDetailsController = Depends(get_str_cribs_controller),
):
    return await controller.update(record_id, data)


@router.delete("/str-cribs/fee-details/{record_id}", tags=["str-cribs"])
async def delete_str_cribs_fee_detail(
    record_id: int,
    controller: StrCribsFeeDetailsController = Depends(get_str_cribs_controller),
):
    return await controller.delete(record_id)


