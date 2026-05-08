from fastapi import APIRouter, Depends

from app.external_api.controllers.external_api_controller import ExternalApiController
from app.external_api.services.external_api_service import ExternalApiService

router = APIRouter(prefix="/external-api", tags=["external-api"])


def get_controller() -> ExternalApiController:
    return ExternalApiController(ExternalApiService())


@router.get("/mortgage-rate")
async def get_30y_fixed_rate(
    controller: ExternalApiController = Depends(get_controller),
):
    return await controller.get_30y_fixed_rate()
