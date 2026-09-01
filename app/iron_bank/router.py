import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_config
from app.core.database import get_db
from app.core.reference_data.repository import ReferenceDataRepository
from app.core.reference_data.service import ReferenceDataService
from app.dependencies import get_current_user
from app.iron_bank.controllers.create_underwriting_from_url_controller import (
    CreateUnderwritingFromUrlController,
)
from app.iron_bank.controllers.deal_status_controller import DealStatusController
from app.iron_bank.controllers.duplicate_underwriting_controller import (
    DuplicateUnderwritingController,
)
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
from app.iron_bank.schemas.duplicate_underwriting import (
    DuplicateUnderwritingResult,
)
from app.iron_bank.schemas.deal_status import (
    DealStatusOptionsResult,
    DealStatusTransitionsResult,
    UpdateDealStatusPayload,
    UpdateDealStatusResult,
)
from app.iron_bank.schemas.get_underwriting import (
    DealTagOptionsResult,
    GetUnderwritingEditContextResult,
    GetUnderwritingsQuery,
    GetUnderwritingsResult,
)
from app.iron_bank.schemas.prepare_uw import BedroomContext, PrepareUwDataResult
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
from app.iron_bank.services.duplicate_underwriting_service import (
    DuplicateUnderwritingService,
)
from app.iron_bank.services.get_underwriting_service import GetUnderwritingService
from app.iron_bank.services.simulate_underwritings_service import (
    SimulateUnderwritingsService,
)
from app.iron_bank.services.deal_status_service import DealStatusService
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService
from app.iron_bank.services.update_underwriting_service import UpdateUnderwritingService
from app.iron_bank.repositories.job_repository import JobRepository
from app.workflows.prepare_uw_data_job import PrepareUwDataJob
import app.iron_bank.models  # noqa: F401 — ensures all models are registered with SQLAlchemy

router = APIRouter(prefix="/iron-bank", tags=["iron_bank"])


def _opex_by_bedrooms_service(db: AsyncSession):
    """Supplies the market's annual RE appreciation rate to the save/update path."""
    from app.markets.repositories.market_repository import MarketRepository
    from app.markets.repositories.opex_repository import OpexByBedroomsRepository
    from app.markets.services.opex_service import OpexByBedroomsService

    return OpexByBedroomsService(OpexByBedroomsRepository(db), MarketRepository(db))


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
    from app.markets.repositories.construction_repository import (
        ConstructionAmenitiesRepository,
    )
    from app.markets.repositories.market_repository import MarketRepository
    from app.markets.repositories.realtor_repository import RealtorRepository
    from app.markets.services.market_service import MarketService
    from app.zillow.repositories.scheduled_listings_repository import (
        ScheduledListingsRepository,
    )
    from app.zillow.services.scheduled_listings_service import ScheduledListingsService

    return SaveUnderwritingController(
        SaveUnderwritingService(
            UnderwritingRepository(db),
            market_service=MarketService(
                MarketRepository(db),
                ConstructionAmenitiesRepository(db),
                RealtorRepository(db),
            ),
            listings_service=ScheduledListingsService(ScheduledListingsRepository(db)),
            cleaned_data_service=CleanedDataService(CleanedDataRepository(db)),
            reference_data_service=ReferenceDataService(ReferenceDataRepository(db)),
            opex_service=_opex_by_bedrooms_service(db),
        )
    )


def get_create_underwriting_from_url_controller(
    db: AsyncSession = Depends(get_db),
) -> CreateUnderwritingFromUrlController:
    from app.airbnb_public.repositories.cleaned_data_repository import (
        CleanedDataRepository,
    )
    from app.airbnb_public.services.cleaned_data_service import CleanedDataService
    from app.external_api.services.zillow_property_service import (
        ZillowPropertyService,
    )
    from app.markets.repositories.construction_repository import (
        ConstructionAmenitiesRepository,
    )
    from app.markets.repositories.market_repository import MarketRepository
    from app.markets.repositories.realtor_repository import RealtorRepository
    from app.markets.services.market_service import MarketService
    from app.zillow.repositories.scheduled_listings_repository import (
        ScheduledListingsRepository,
    )
    from app.zillow.services.scheduled_listings_service import ScheduledListingsService

    repository = UnderwritingRepository(db)
    market_service = MarketService(
        MarketRepository(db),
        ConstructionAmenitiesRepository(db),
        RealtorRepository(db),
    )
    return CreateUnderwritingFromUrlController(
        CreateUnderwritingFromUrlService(
            zillow_property_service=ZillowPropertyService(),
            # market_service + cleaned_data_service let the save estimate
            # forecasted revenue from Airbnb comps now that this flow carries a
            # market_id; bedrooms come off the stored zillow_property.
            save_service=SaveUnderwritingService(
                repository,
                market_service=market_service,
                cleaned_data_service=CleanedDataService(CleanedDataRepository(db)),
                opex_service=_opex_by_bedrooms_service(db),
            ),
            underwriting_reader=repository,
            market_context_reader=PrepareUwDataJob.from_session(db),
            market_name_reader=market_service,
            # Fetching property details also persists the listing to
            # scheduled_listings, so this both verifies the scrape completed and
            # lets the row carry a real zpid instead of a null one.
            listings_service=ScheduledListingsService(ScheduledListingsRepository(db)),
        )
    )


def get_duplicate_underwriting_controller(
    db: AsyncSession = Depends(get_db),
) -> DuplicateUnderwritingController:
    return DuplicateUnderwritingController(
        DuplicateUnderwritingService(UnderwritingRepository(db))
    )


def get_update_underwriting_controller(
    db: AsyncSession = Depends(get_db),
) -> UpdateUnderwritingController:
    from app.airbnb_public.repositories.cleaned_data_repository import (
        CleanedDataRepository,
    )
    from app.airbnb_public.services.cleaned_data_service import CleanedDataService
    from app.external_api.services.n8n_webhook_service import N8nWebhookService
    from app.markets.repositories.construction_repository import (
        ConstructionAmenitiesRepository,
    )
    from app.markets.repositories.market_repository import MarketRepository
    from app.markets.repositories.realtor_repository import RealtorRepository
    from app.markets.services.market_service import MarketService
    from app.users.repositories.user_repository import UserRepository
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

    config = get_config()
    return UpdateUnderwritingController(
        UpdateUnderwritingService(
            UnderwritingRepository(db),
            market_service=MarketService(
                MarketRepository(db),
                ConstructionAmenitiesRepository(db),
                RealtorRepository(db),
            ),
            listings_service=ScheduledListingsService(ScheduledListingsRepository(db)),
            listing_details_service=ScheduledListingDetailsService(
                ScheduledListingDetailsRepository(db)
            ),
            cleaned_data_service=CleanedDataService(CleanedDataRepository(db)),
            reference_data_service=ReferenceDataService(ReferenceDataRepository(db)),
            user_repository=UserRepository(db),
            present_to_clients_webhook_service=N8nWebhookService(
                url=config.N8N_WEBHOOK_PRESENT_TO_CLIENTS_URL,
                enabled=config.N8N_WEBHOOK_PRESENT_TO_CLIENTS_ENABLED,
            ),
            analyst_completed_webhook_service=N8nWebhookService(
                url=config.N8N_WEBHOOK_ANALYST_COMPLETED_URL,
                enabled=config.N8N_WEBHOOK_ANALYST_COMPLETED_ENABLED,
            ),
            opex_service=_opex_by_bedrooms_service(db),
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
    from app.markets.repositories.opex_repository import (
        OpexByBedroomsRepository,
        OpexBySizeRepository,
    )
    from app.markets.repositories.realtor_repository import RealtorRepository
    from app.markets.repositories.str_cribs_repository import (
        StrCribsFeeDetailsRepository,
    )
    from app.users.repositories.user_repository import UserRepository
    from app.markets.services.construction_service import (
        ConstructionAmenitiesService,
        ConstructionRemodelingService,
    )
    from app.markets.services.str_cribs_service import StrCribsFeeDetailsService
    from app.markets.services.opex_service import (
        OpexByBedroomsService,
        OpexBySizeService,
    )
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
    # Shared dependency set so the normal list service and the simulation
    # service can never drift apart: the simulation service is the read
    # service plus a calculator, and the page it returns is enriched (zillow
    # hydration, reference labels) identically to the normal list.
    service_deps = dict(
        listings_service=ScheduledListingsService(ScheduledListingsRepository(db)),
        listing_details_service=ScheduledListingDetailsService(
            ScheduledListingDetailsRepository(db)
        ),
        opex_by_bedrooms_service=OpexByBedroomsService(
            OpexByBedroomsRepository(db), market_repo
        ),
        opex_by_size_service=OpexBySizeService(OpexBySizeRepository(db), market_repo),
        construction_amenities_service=ConstructionAmenitiesService(
            ConstructionAmenitiesRepository(db)
        ),
        construction_remodeling_service=ConstructionRemodelingService(
            ConstructionRemodelingRepository(db)
        ),
        str_cribs_service=StrCribsFeeDetailsService(StrCribsFeeDetailsRepository(db)),
        reference_data_service=ReferenceDataService(ReferenceDataRepository(db)),
        user_repository=UserRepository(db),
        market_repository=market_repo,
        realtor_repository=RealtorRepository(db),
    )
    return GetUnderwritingController(
        GetUnderwritingService(UnderwritingRepository(db), **service_deps),
        simulation_service=SimulateUnderwritingsService(
            UnderwritingRepository(db), **service_deps
        ),
    )


@router.get("/prepare-uw-data", response_model=PrepareUwDataResult, tags=["iron_bank"])
async def get_prepare_uw_data(
    zpid: str = Query(...),
    controller: PrepareUwDataController = Depends(get_prepare_uw_data_controller),
):
    return await controller.get_prepare_uw_data(zpid=zpid)


@router.get(
    "/underwritings/{underwriting_id}/bedroom-context",
    response_model=BedroomContext,
    tags=["iron_bank"],
)
async def get_bedroom_context(
    underwriting_id: int,
    bedrooms: int = Query(...),
    controller: PrepareUwDataController = Depends(get_prepare_uw_data_controller),
):
    """Re-seed an underwriting's bedroom-keyed values for a new bedroom count.

    ``bedrooms`` is the *prospective* count the analyst is considering — not the
    one stored on the row, which is exactly what this previews changing. The
    market and purchase price are read off the underwriting itself, so the
    property-tax blob can never be computed against a stale price the client
    happened to be holding.

    404s when the underwriting does not exist, has no market, or its market has
    no opex row at that bedroom count.

    Returns only what is keyed on (market, bedrooms). The sqft-keyed opex rows,
    the "Design / Project Management" item and the market's must-have amenities
    are not in the response and must survive untouched.

    ``operating_expenses`` and ``construction_amenities`` use the same field
    names and item shapes as the edit-context response, but both are **partial**
    — only what a bedroom change moves. Do not treat either as a replacement for
    the list it shares a name with.

    ``operating_expenses`` carries this underwriting's own row ids: apply each
    entry to the row with that id, and treat ``id: null`` as a row to add. Then
    PUT the **full** merged array — rows absent from an update payload are
    deleted, so sending only these would drop the rest.
    """
    return await controller.get_bedroom_context(
        underwriting_id=underwriting_id,
        bedrooms=bedrooms,
    )


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
    current_user=Depends(get_current_user),
):
    return await controller.create_from_url(
        url=payload.url,
        market_id=payload.market_id,
        current_user_id=current_user.id,
    )


@router.post(
    "/underwritings/{underwriting_id}/duplicate",
    response_model=DuplicateUnderwritingResult,
    status_code=201,
    tags=["iron_bank"],
)
async def duplicate_underwriting(
    underwriting_id: int,
    controller: DuplicateUnderwritingController = Depends(
        get_duplicate_underwriting_controller
    ),
    current_user=Depends(get_current_user),
):
    return await controller.duplicate_underwriting(
        underwriting_id=underwriting_id,
        current_user_id=current_user.id,
    )


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


@router.get(
    "/deal-tag-options",
    response_model=DealTagOptionsResult,
    tags=["iron_bank"],
)
async def get_deal_tag_options(
    controller: GetUnderwritingController = Depends(get_get_underwriting_controller),
):
    return await controller.get_deal_tag_options()


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
