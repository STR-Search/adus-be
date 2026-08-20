import pytest
from fastapi import HTTPException
from pydantic import BaseModel

from app.iron_bank.controllers.prepare_uw_data_controller import (
    PrepareUwDataController,
)
from app.workflows.prepare_uw_data_job import BedroomContextNotFoundError


class ExplodingJob:
    def __init__(self, error):
        self.error = error

    async def build_bedroom_context(self, **kwargs):
        raise self.error


def _controller(error):
    return PrepareUwDataController(ExplodingJob(error))


@pytest.mark.asyncio
async def test_missing_opex_row_is_a_404():
    controller = _controller(
        BedroomContextNotFoundError("No opex data for market 3 at 7 bedrooms")
    )

    with pytest.raises(HTTPException) as exc:
        await controller.get_bedroom_context(underwriting_id=42, bedrooms=7)

    assert exc.value.status_code == 404
    assert exc.value.detail == "No opex data for market 3 at 7 bedrooms"


@pytest.mark.asyncio
async def test_a_malformed_opex_row_is_a_500_not_a_404():
    # pydantic's ValidationError subclasses ValueError, so a controller that
    # mapped ValueError -> 404 would report unparseable market data as "no data
    # at that bedroom count" and dump the pydantic error into the detail string.
    class Model(BaseModel):
        bedrooms: int

    try:
        Model.model_validate({"bedrooms": "not-a-number"})
    except Exception as validation_error:  # noqa: BLE001 — captured for reuse
        controller = _controller(validation_error)

    with pytest.raises(HTTPException) as exc:
        await controller.get_bedroom_context(underwriting_id=42, bedrooms=5)

    assert exc.value.status_code == 500
    assert exc.value.detail == "Failed to fetch bedroom context"


@pytest.mark.asyncio
async def test_an_unexpected_error_is_a_500():
    controller = _controller(RuntimeError("connection reset"))

    with pytest.raises(HTTPException) as exc:
        await controller.get_bedroom_context(underwriting_id=42, bedrooms=5)

    assert exc.value.status_code == 500
    # the internal message is logged, not leaked to the caller
    assert exc.value.detail == "Failed to fetch bedroom context"
