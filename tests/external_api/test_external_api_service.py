import pytest

from app.external_api.schemas.external_api import MortgageRateResponse
from app.external_api.services.external_api_service import ExternalApiService


class _CountingService(ExternalApiService):
    """Counts _fetch calls and returns a scripted sequence of results."""

    def __init__(self, results):
        super().__init__()
        self._results = list(results)
        self.fetch_calls = 0

    async def _fetch_30y_fixed_rate(self):
        self.fetch_calls += 1
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_successful_rate_is_fetched_once_and_memoized():
    rate = MortgageRateResponse(value=6.5, date="2026-06-01")
    service = _CountingService([rate])

    first = await service.get_30y_fixed_rate()
    second = await service.get_30y_fixed_rate()

    assert first is rate
    assert second is rate
    # A batch reusing one service hits FRED only once.
    assert service.fetch_calls == 1


@pytest.mark.asyncio
async def test_failed_fetch_is_not_cached_and_retries_until_success():
    rate = MortgageRateResponse(value=6.5, date="2026-06-01")
    # First attempt fails (None), second recovers.
    service = _CountingService([None, rate])

    first = await service.get_30y_fixed_rate()
    second = await service.get_30y_fixed_rate()

    assert first is None
    assert second is rate
    # A None result is not cached, so the next listing retries.
    assert service.fetch_calls == 2
