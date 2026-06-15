from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.iron_bank.controllers.get_underwriting_controller import GetUnderwritingController
from app.iron_bank.controllers.prepare_uw_data_controller import PrepareUwDataController
from app.iron_bank.controllers.save_underwriting_controller import SaveUnderwritingController
from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.schemas.get_underwriting import GetUnderwritingEditContextResult, GetUnderwritingsResult
from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload, SaveUnderwritingResult
from app.iron_bank.services.get_underwriting_service import GetUnderwritingService
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService
from app.workflows.prepare_uw_data_job import PrepareUwDataJob
import app.iron_bank.models  # noqa: F401 — ensures all models are registered with SQLAlchemy

router = APIRouter(prefix="/iron-bank", tags=["iron_bank"])


def get_prepare_uw_data_controller(db: AsyncSession = Depends(get_db)) -> PrepareUwDataController:
    return PrepareUwDataController(PrepareUwDataJob.from_session(db))


def get_save_underwriting_controller(db: AsyncSession = Depends(get_db)) -> SaveUnderwritingController:
    return SaveUnderwritingController(
        SaveUnderwritingService(UnderwritingRepository(db))
    )


def get_get_underwriting_controller(db: AsyncSession = Depends(get_db)) -> GetUnderwritingController:
    from app.markets.repositories.construction_repository import (
        ConstructionAmenitiesRepository,
        ConstructionRemodelingRepository,
    )
    from app.markets.repositories.market_repository import MarketRepository
    from app.markets.repositories.opex_repository import OpexByBedroomsRepository
    from app.markets.services.construction_service import (
        ConstructionAmenitiesService,
        ConstructionRemodelingService,
    )
    from app.markets.services.opex_service import OpexByBedroomsService
    from app.zillow.repositories.scheduled_listings_repository import ScheduledListingsRepository
    from app.zillow.services.scheduled_listings_service import ScheduledListingsService

    market_repo = MarketRepository(db)
    return GetUnderwritingController(
        GetUnderwritingService(UnderwritingRepository(db)),
        ConstructionAmenitiesService(ConstructionAmenitiesRepository(db)),
        ConstructionRemodelingService(ConstructionRemodelingRepository(db)),
        ScheduledListingsService(ScheduledListingsRepository(db)),
        OpexByBedroomsService(OpexByBedroomsRepository(db), market_repo),
    )


@router.get("/prepare-uw-data", tags=["iron_bank"])
async def get_prepare_uw_data(
    zpid: str = Query(...),
    controller: PrepareUwDataController = Depends(get_prepare_uw_data_controller),
):
    return await controller.get_prepare_uw_data(zpid=zpid)


@router.post("/underwritings", response_model=SaveUnderwritingResult, tags=["iron_bank"])
async def save_underwriting(
    payload: SaveUnderwritingPayload,
    controller: SaveUnderwritingController = Depends(get_save_underwriting_controller),
):
    return await controller.save_underwriting(payload)


@router.get("/underwritings", response_model=GetUnderwritingsResult, tags=["iron_bank"])
async def get_underwritings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=20),
    zpid: str | None = Query(None),
    market_id: int | None = Query(None),
    controller: GetUnderwritingController = Depends(get_get_underwriting_controller),
):
    return await controller.get_underwritings(
        page=page,
        page_size=page_size,
        zpid=zpid,
        market_id=market_id,
    )


@router.get(
    "/underwritings/{underwriting_id}",
    response_model=GetUnderwritingEditContextResult,
    tags=["iron_bank"],
)
async def get_underwriting(
    underwriting_id: int,
    controller: GetUnderwritingController = Depends(get_get_underwriting_controller),
):
    return await controller.get_underwriting(underwriting_id)
