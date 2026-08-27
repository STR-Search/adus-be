import pytest
from fastapi import HTTPException

from app.iron_bank.controllers.create_underwriting_from_url_controller import (
    CreateUnderwritingFromUrlController,
)
from app.iron_bank.services.create_underwriting_from_url_service import (
    ListingMarketMismatchError,
    ListingNotScrapedError,
    UnderwritingAlreadyExistsError,
)

URL = "https://www.zillow.com/homedetails/26110417_zpid/"


class FailingService:
    def __init__(self, error):
        self.error = error

    async def create(self, *, url, market_id=None, current_user_id=None):
        raise self.error


def _controller(error):
    return CreateUnderwritingFromUrlController(FailingService(error))


@pytest.mark.asyncio
async def test_market_mismatch_maps_to_409_with_the_id_to_resubmit():
    controller = _controller(
        ListingMarketMismatchError(
            requested_market_id=5,
            listing_market_id=3,
            listing_market_name="Austin, TX",
            zpid="26110417",
        )
    )

    with pytest.raises(HTTPException) as exc:
        await controller.create_from_url(url=URL, market_id=5)

    assert exc.value.status_code == 409
    assert exc.value.detail["requested_market_id"] == 5
    assert exc.value.detail["listing_market_id"] == 3
    assert exc.value.detail["listing_market_name"] == "Austin, TX"
    assert exc.value.detail["zpid"] == "26110417"
    assert "market_id=3" in exc.value.detail["message"]


@pytest.mark.asyncio
async def test_an_unnamed_market_still_maps_to_an_actionable_409():
    controller = _controller(
        ListingMarketMismatchError(
            requested_market_id=5, listing_market_id=3, zpid="26110417"
        )
    )

    with pytest.raises(HTTPException) as exc:
        await controller.create_from_url(url=URL, market_id=5)

    assert exc.value.status_code == 409
    # the key is always present, so clients can branch on null rather than
    # on its absence
    assert exc.value.detail["listing_market_name"] is None
    assert exc.value.detail["listing_market_id"] == 3


@pytest.mark.asyncio
async def test_market_mismatch_on_a_null_request_still_carries_the_correct_id():
    controller = _controller(
        ListingMarketMismatchError(
            requested_market_id=None, listing_market_id=3, zpid="26110417"
        )
    )

    with pytest.raises(HTTPException) as exc:
        await controller.create_from_url(url=URL)

    assert exc.value.status_code == 409
    assert exc.value.detail["requested_market_id"] is None
    assert exc.value.detail["listing_market_id"] == 3


@pytest.mark.asyncio
async def test_market_mismatch_does_not_fall_through_to_the_generic_handlers():
    """A structured 409, not a stringified 400 or an opaque 500."""
    controller = _controller(
        ListingMarketMismatchError(
            requested_market_id=5, listing_market_id=3, zpid=None
        )
    )

    with pytest.raises(HTTPException) as exc:
        await controller.create_from_url(url=URL, market_id=5)

    assert exc.value.status_code not in (400, 500)
    assert isinstance(exc.value.detail, dict)


@pytest.mark.asyncio
async def test_existing_mappings_are_unchanged():
    duplicate = _controller(UnderwritingAlreadyExistsError(77))
    with pytest.raises(HTTPException) as exc:
        await duplicate.create_from_url(url=URL)
    assert exc.value.status_code == 409
    assert exc.value.detail["underwriting_id"] == 77

    not_scraped = _controller(ListingNotScrapedError(URL, "26110417"))
    with pytest.raises(HTTPException) as exc:
        await not_scraped.create_from_url(url=URL)
    assert exc.value.status_code == 422

    bad_input = _controller(ValueError("Could not fetch"))
    with pytest.raises(HTTPException) as exc:
        await bad_input.create_from_url(url=URL)
    assert exc.value.status_code == 400

    unexpected = _controller(RuntimeError("boom"))
    with pytest.raises(HTTPException) as exc:
        await unexpected.create_from_url(url=URL)
    assert exc.value.status_code == 500
