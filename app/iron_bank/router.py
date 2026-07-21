import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.reference_data.repository import ReferenceDataRepository
from app.core.reference_data.service import ReferenceDataService
from app.dependencies import get_current_user
from app.iron_bank.controllers.create_underwriting_from_url_controller import (
    CreateUnderwritingFromUrlController,
)
from app.iron_bank.controllers.deal_status_controller import DealStatusController
from app.iron_bank.controllers.get_underwriting_controller import (
    GetUnderwritingController,
)
from app.iron_bank.controllers.prepare_uw_data_controller import PrepareUwDataController
from app.iron_bank.controllers.save_underwriting_controller import (
    SaveUnderwritingController,
)
from app.iron_bank.controllers.update_underwriting_controller import (
    UpdateUnderwritingController,
)
from app.iron_bank.controllers.workflow_trigger_controller import (
    WorkflowTriggerController,
)
from app.iron_bank.enums import DealStatus
from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.schemas.job import (
    JobCreatedResponse,
    JobStatusResponse,
)
from app.iron_bank.schemas.create_underwriting_from_url import (
    CreateUnderwritingFromUrlPayload,
)
from app.iron_bank.schemas.deal_status import (
    DealStatusOptionsResult,
    DealStatusTransitionsResult,
    UpdateDealStatusPayload,
    UpdateDealStatusResult,
)
from app.iron_bank.schemas.get_underwriting import (
    GetUnderwritingEditContextResult,
    GetUnderwritingsQuery,
    GetUnderwritingsResult,
)
from app.iron_bank.schemas.prepare_uw import PrepareUwDataResult
from app.iron_bank.schemas.save_underwriting import (
    SaveUnderwritingPayload,
    SaveUnderwritingResult,
)
from app.iron_bank.schemas.update_underwriting import (
    UpdateUnderwritingPayload,
    UpdateUnderwritingResult,
)
from app.iron_bank.services.create_underwriting_from_url_service import (
    CreateUnderwritingFromUrlService,
)
from app.iron_bank.services.get_underwriting_service import GetUnderwritingService
from app.iron_bank.services.deal_status_service import DealStatusService
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService
from app.iron_bank.services.update_underwriting_service import UpdateUnderwritingService
from app.iron_bank.repositories.job_repository import JobRepository
from app.workflows.prepare_uw_data_job import PrepareUwDataJob
import app.iron_bank.models  # noqa: F401 — ensures all models are registered with SQLAlchemy

router = APIRouter(prefix="/iron-bank", tags=["iron_bank"])


def get_deal_status_controller() -> DealStatusController:
    return DealStatusController(DealStatusService())


def get_prepare_uw_data_controller(
    db: AsyncSession = Depends(get_db),
) -> PrepareUwDataController:
    return PrepareUwDataController(PrepareUwDataJob.from_session(db))


def get_workflow_trigger_controller(
    db: AsyncSession = Depends(get_db),
) -> WorkflowTriggerController:
    return WorkflowTriggerController(job_repository=JobRepository(db))


def get_save_underwriting_controller(
    db: AsyncSession = Depends(get_db),
) -> SaveUnderwritingController:
    from app.airbnb_public.repositories.cleaned_data_repository import (
        CleanedDataRepository,
    )
    from app.airbnb_public.services.cleaned_data_service import CleanedDataService
    from app.markets.repositories.market_repository import MarketRepository
    from app.markets.services.market_service import MarketService
    from app.zillow.repositories.scheduled_listings_repository import (
        ScheduledListingsRepository,
    )
    from app.zillow.services.scheduled_listings_service import ScheduledListingsService

    return SaveUnderwritingController(
        SaveUnderwritingService(
            UnderwritingRepository(db),
            market_service=MarketService(MarketRepository(db)),
            listings_service=ScheduledListingsService(ScheduledListingsRepository(db)),
            cleaned_data_service=CleanedDataService(CleanedDataRepository(db)),
            reference_data_service=ReferenceDataService(ReferenceDataRepository(db)),
        )
    )


def get_create_underwriting_from_url_controller(
    db: AsyncSession = Depends(get_db),
) -> CreateUnderwritingFromUrlController:
    from app.external_api.services.zillow_property_service import (
        ZillowPropertyService,
    )

    repository = UnderwritingRepository(db)
    return CreateUnderwritingFromUrlController(
        CreateUnderwritingFromUrlService(
            zillow_property_service=ZillowPropertyService(),
            save_service=SaveUnderwritingService(repository),
            underwriting_reader=repository,
        )
    )


def get_update_underwriting_controller(
    db: AsyncSession = Depends(get_db),
) -> UpdateUnderwritingController:
    from app.airbnb_public.repositories.cleaned_data_repository import (
        CleanedDataRepository,
    )
    from app.airbnb_public.services.cleaned_data_service import CleanedDataService
    from app.external_api.services.n8n_webhook_service import N8nWebhookService
    from app.markets.repositories.market_repository import MarketRepository
    from app.markets.services.market_service import MarketService
    from app.zillow.repositories.scheduled_listings_repository import (
        ScheduledListingsRepository,
    )
    from app.zillow.services.scheduled_listings_service import ScheduledListingsService

    return UpdateUnderwritingController(
        UpdateUnderwritingService(
            UnderwritingRepository(db),
            market_service=MarketService(MarketRepository(db)),
            listings_service=ScheduledListingsService(ScheduledListingsRepository(db)),
            cleaned_data_service=CleanedDataService(CleanedDataRepository(db)),
            reference_data_service=ReferenceDataService(ReferenceDataRepository(db)),
            n8n_webhook_service=N8nWebhookService(),
        )
    )


def get_get_underwriting_controller(
    db: AsyncSession = Depends(get_db),
) -> GetUnderwritingController:
    from app.markets.repositories.construction_repository import (
        ConstructionAmenitiesRepository,
        ConstructionRemodelingRepository,
    )
    from app.markets.repositories.market_repository import MarketRepository
    from app.markets.repositories.opex_repository import OpexByBedroomsRepository
    from app.markets.repositories.str_cribs_repository import (
        StrCribsFeeDetailsRepository,
    )
    from app.markets.services.construction_service import (
        ConstructionAmenitiesService,
        ConstructionRemodelingService,
    )
    from app.markets.services.str_cribs_service import StrCribsFeeDetailsService
    from app.markets.services.opex_service import OpexByBedroomsService
    from app.zillow.repositories.scheduled_listing_details_repository import (
        ScheduledListingDetailsRepository,
    )
    from app.zillow.repositories.scheduled_listings_repository import (
        ScheduledListingsRepository,
    )
    from app.zillow.services.scheduled_listing_details_service import (
        ScheduledListingDetailsService,
    )
    from app.zillow.services.scheduled_listings_service import ScheduledListingsService

    market_repo = MarketRepository(db)
    return GetUnderwritingController(
        GetUnderwritingService(
            UnderwritingRepository(db),
            listings_service=ScheduledListingsService(ScheduledListingsRepository(db)),
            listing_details_service=ScheduledListingDetailsService(
                ScheduledListingDetailsRepository(db)
            ),
            opex_by_bedrooms_service=OpexByBedroomsService(
                OpexByBedroomsRepository(db), market_repo
            ),
            construction_amenities_service=ConstructionAmenitiesService(
                ConstructionAmenitiesRepository(db)
            ),
            construction_remodeling_service=ConstructionRemodelingService(
                ConstructionRemodelingRepository(db)
            ),
            str_cribs_service=StrCribsFeeDetailsService(
                StrCribsFeeDetailsRepository(db)
            ),
            reference_data_service=ReferenceDataService(ReferenceDataRepository(db)),
        )
    )


@router.get("/prepare-uw-data", response_model=PrepareUwDataResult, tags=["iron_bank"])
async def get_prepare_uw_data(
    zpid: str = Query(...),
    controller: PrepareUwDataController = Depends(get_prepare_uw_data_controller),
):
    return await controller.get_prepare_uw_data(zpid=zpid)


@router.post(
    "/underwritings/batch-prepare-by-market",
    response_model=JobCreatedResponse,
    status_code=202,
    tags=["iron_bank"],
)
async def batch_prepare_underwritings_by_market(
    background: BackgroundTasks,
    market_id: int = Query(...),
    since_hours: int = Query(..., ge=1),
    limit: int | None = Query(None, ge=1),
    controller: WorkflowTriggerController = Depends(get_workflow_trigger_controller),
):
    return await controller.batch_prepare_by_market(
        market_id=market_id,
        since_hours=since_hours,
        limit=limit,
        background=background,
    )


@router.post(
    "/underwritings/batch-prepare-by-preset",
    response_model=JobCreatedResponse,
    status_code=202,
    tags=["iron_bank"],
)
async def batch_prepare_underwritings_by_preset(
    background: BackgroundTasks,
    preset_id: uuid.UUID = Query(...),
    since_hours: int = Query(..., ge=1),
    limit: int | None = Query(None, ge=1),
    controller: WorkflowTriggerController = Depends(get_workflow_trigger_controller),
):
    return await controller.batch_prepare_by_preset(
        preset_id=preset_id,
        since_hours=since_hours,
        limit=limit,
        background=background,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    tags=["iron_bank"],
)
async def get_job(
    job_id: uuid.UUID,
    controller: WorkflowTriggerController = Depends(get_workflow_trigger_controller),
):
    return await controller.get_job(job_id)


@router.get(
    "/deal-statuses",
    response_model=DealStatusOptionsResult,
    tags=["iron_bank"],
)
async def get_deal_statuses(
    controller: DealStatusController = Depends(get_deal_status_controller),
):
    return controller.get_deal_statuses()


@router.get(
    "/deal-statuses/transitions",
    response_model=DealStatusTransitionsResult,
    tags=["iron_bank"],
)
async def get_deal_status_transitions(
    current_status: DealStatus,
    actor_role: str,
    controller: DealStatusController = Depends(get_deal_status_controller),
):
    return controller.get_allowed_transitions(
        current_status=current_status,
        actor_role=actor_role,
    )


@router.post(
    "/underwritings", response_model=SaveUnderwritingResult, tags=["iron_bank"]
)
async def save_underwriting(
    payload: SaveUnderwritingPayload,
    controller: SaveUnderwritingController = Depends(get_save_underwriting_controller),
):
    return await controller.save_underwriting(payload)


@router.post(
    "/underwritings/from-zillow-url",
    response_model=SaveUnderwritingResult,
    tags=["iron_bank"],
)
async def create_underwriting_from_url(
    payload: CreateUnderwritingFromUrlPayload,
    controller: CreateUnderwritingFromUrlController = Depends(
        get_create_underwriting_from_url_controller
    ),
):
    return await controller.create_from_url(url=payload.url)


@router.put(
    "/underwritings/{underwriting_id}",
    response_model=UpdateUnderwritingResult,
    tags=["iron_bank"],
)
async def update_underwriting(
    underwriting_id: int,
    payload: UpdateUnderwritingPayload,
    controller: UpdateUnderwritingController = Depends(
        get_update_underwriting_controller
    ),
):
    return await controller.update_underwriting(underwriting_id, payload)


@router.patch(
    "/underwritings/{underwriting_id}/deal-status",
    response_model=UpdateDealStatusResult,
    tags=["iron_bank"],
)
async def update_underwriting_deal_status(
    underwriting_id: int,
    payload: UpdateDealStatusPayload,
    controller: UpdateUnderwritingController = Depends(
        get_update_underwriting_controller
    ),
    current_user=Depends(get_current_user),
):
    return await controller.update_deal_status(
        underwriting_id=underwriting_id,
        deal_status=payload.deal_status,
        actor_user_id=current_user.id,
    )


@router.get("/underwritings", response_model=GetUnderwritingsResult, tags=["iron_bank"])
async def get_underwritings(
    filters: Annotated[GetUnderwritingsQuery, Query()],
    controller: GetUnderwritingController = Depends(get_get_underwriting_controller),
):
    return await controller.get_underwritings(**filters.model_dump())


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
