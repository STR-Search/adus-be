import pytest

from app.external_api.schemas.zillow_property_details import ZillowPropertyDetails
from app.external_api.services.zillow_property_service import ZillowPropertyService

# A trimmed slice of the real /api/property-details response shape.
SAMPLE_PROPERTY = {
    "zpid": "26110417",
    "price": 389000.0,
    "street_address": "727 N Pine St",
    "city": "San Antonio",
    "state": "TX",
    "zipcode": "78202",
    "bedrooms": 5,
    "bathrooms": 4.0,
    "living_area": 4608,
    "lot_size_sqft": 10698.0,
    "original_photos": [
        {
            "caption": "",
            "mixedSources": {
                "jpeg": [
                    {"url": "https://photos.zillowstatic.com/fp/a-d_d.jpg", "width": 800},
                    {"url": "https://photos.zillowstatic.com/fp/a-o_a.jpg", "width": 1024},
                ],
                "webp": [
                    {"url": "https://photos.zillowstatic.com/fp/a-d_d.webp", "width": 800},
                ],
            },
        }
    ],
    "year_built": 1927,  # extra field — must be tolerated, not mapped
}

PROPERTY_URL = (
    "https://www.zillow.com/homedetails/"
    "727-N-Pine-St-San-Antonio-TX-78202/26110417_zpid/"
)


def _service() -> ZillowPropertyService:
    # __init__ only reads config defaults (empty strings); that's fine for
    # exercising the pure mapping helpers.
    return ZillowPropertyService()


def test_to_zillow_property_maps_canonical_shape():
    details = ZillowPropertyDetails.model_validate(SAMPLE_PROPERTY)

    result = _service()._to_zillow_property(details, url=PROPERTY_URL)

    assert result == {
        "id": "26110417",
        "url": PROPERTY_URL,
        "thumbnail": "https://photos.zillowstatic.com/fp/a-d_d.jpg",
        "price": 389000.0,
        "address": "727 N Pine St, San Antonio, TX 78202",
        "bedrooms": 5,
        "bathrooms": 4.0,
        "area": 4608,
        "original_photos": SAMPLE_PROPERTY["original_photos"],
        "lot_size_sqft": 10698.0,
    }


def test_to_zillow_property_stringifies_numeric_zpid():
    details = ZillowPropertyDetails.model_validate({**SAMPLE_PROPERTY, "zpid": 26110417})

    result = _service()._to_zillow_property(details, url=PROPERTY_URL)

    assert result["id"] == "26110417"


def test_to_zillow_property_tolerates_missing_photos():
    details = ZillowPropertyDetails.model_validate(
        {**SAMPLE_PROPERTY, "original_photos": None}
    )

    result = _service()._to_zillow_property(details, url=PROPERTY_URL)

    assert result["thumbnail"] is None
    assert result["original_photos"] is None


def test_first_property_unwraps_data_list():
    service = _service()

    details = service._first_property({"data": [SAMPLE_PROPERTY]}, url=PROPERTY_URL)

    assert details is not None
    assert details.zpid == "26110417"


def test_first_property_accepts_bare_list():
    service = _service()

    details = service._first_property([SAMPLE_PROPERTY], url=PROPERTY_URL)

    assert details is not None
    assert details.zpid == "26110417"


def test_first_property_returns_none_on_empty():
    service = _service()

    assert service._first_property({"data": []}, url=PROPERTY_URL) is None
    assert service._first_property([], url=PROPERTY_URL) is None


@pytest.mark.asyncio
async def test_fetch_returns_none_when_not_configured():
    # Force missing credentials regardless of the ambient .env so the client
    # short-circuits without making any network call.
    service = _service()
    service.api_base = ""
    service.supabase_url = ""
    service.supabase_anon_key = ""
    service.service_email = ""
    service.service_password = ""

    result = await service.fetch_property_details(url=PROPERTY_URL)

    assert result is None
