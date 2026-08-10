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
    "description": "Charming bungalow near downtown.",
    "year_built": 1927,  # extra field — must be tolerated, not mapped
}

PROPERTY_URL = (
    "https://www.zillow.com/homedetails/"
    "727-N-Pine-St-San-Antonio-TX-78202/26110417_zpid/"
)


async def _no_sleep(_seconds):
    return None


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
        "street": "727 N Pine St",
        "city": "San Antonio",
        "state": "TX",
        "bedrooms": 5,
        "bathrooms": 4.0,
        "area": 4608,
        "original_photos": SAMPLE_PROPERTY["original_photos"],
        "lot_size_sqft": 10698.0,
        "description": "Charming bungalow near downtown.",
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
    service.api_key = ""

    result = await service.fetch_property_details(url=PROPERTY_URL)

    assert result is None


class _StubResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def json(self):  # pragma: no cover - never reached for error codes
        return {"data": []}


class _StubClient:
    """Stands in for ``httpx.AsyncClient``, counting POSTs."""

    def __init__(self, status_code: int, calls: list):
        self._status_code = status_code
        self._calls = calls

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, endpoint, **kwargs):
        self._calls.append(endpoint)
        return _StubResponse(self._status_code)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_fetch_does_not_retry_when_key_is_rejected(monkeypatch, status_code):
    # A static API key can't become valid mid-loop, so a rejection must fail
    # fast rather than burn all _MAX_ATTEMPTS.
    calls: list = []
    monkeypatch.setattr(
        "app.external_api.services.zillow_property_service.httpx.AsyncClient",
        _StubClient(status_code, calls),
    )
    service = _service()
    service.api_base = "https://zillow.example.com"
    service.api_key = "bad-key"

    result = await service.fetch_property_details(url=PROPERTY_URL)

    assert result is None
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_fetch_retries_on_server_error(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        "app.external_api.services.zillow_property_service.httpx.AsyncClient",
        _StubClient(500, calls),
    )
    monkeypatch.setattr(
        "app.external_api.services.zillow_property_service.asyncio.sleep",
        _no_sleep,
    )
    service = _service()
    service.api_base = "https://zillow.example.com"
    service.api_key = "good-key"

    result = await service.fetch_property_details(url=PROPERTY_URL)

    assert result is None
    assert len(calls) == 3
