from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.reference_data.controller import ReferenceDataController
from app.core.reference_data.repository import ReferenceDataRepository
from app.core.reference_data.schemas import (
    CreateEnumOptionPayload,
    EnumOptionRead,
    ReferenceDataResult,
    SetCodesResult,
    UpdateEnumOptionPayload,
)
from app.core.reference_data.service import ReferenceDataService

router = APIRouter(tags=["reference-data"])


def get_reference_data_controller(
    db: AsyncSession = Depends(get_db),
) -> ReferenceDataController:
    return ReferenceDataController(
        ReferenceDataService(ReferenceDataRepository(db))
    )


@router.get("/reference-data", response_model=ReferenceDataResult)
async def get_reference_data(
    domain: str | None = Query(None),
    sets: str | None = Query(
        None, description="Comma-separated set_codes; all sets if omitted"
    ),
    controller: ReferenceDataController = Depends(get_reference_data_controller),
):
    set_codes = (
        [code.strip() for code in sets.split(",") if code.strip()]
        if sets
        else None
    )
    return await controller.get_reference_data(domain=domain, set_codes=set_codes)


@router.get("/reference-data/sets", response_model=SetCodesResult)
async def get_reference_data_sets(
    domain: str | None = Query(None),
    controller: ReferenceDataController = Depends(get_reference_data_controller),
):
    return await controller.get_set_codes(domain=domain)


@router.post("/reference-data/options", response_model=EnumOptionRead, status_code=201)
async def create_reference_option(
    payload: CreateEnumOptionPayload,
    controller: ReferenceDataController = Depends(get_reference_data_controller),
):
    return await controller.create_option(payload)


@router.patch("/reference-data/options/{option_id}", response_model=EnumOptionRead)
async def update_reference_option(
    option_id: int,
    payload: UpdateEnumOptionPayload,
    controller: ReferenceDataController = Depends(get_reference_data_controller),
):
    return await controller.update_option(option_id, payload)
