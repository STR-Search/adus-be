import asyncio

import httpx

from app.core.config import get_config
from app.external_api.schemas.external_api import MortgageRateResponse

_FRED_URL = (
    "https://api.stlouisfed.org/fred/series/observations"
    "?series_id=MORTGAGE30US&file_type=json&sort_order=desc&limit=10"
)


class ExternalApiService:
    def __init__(self):
        self.fred_api_key = get_config().FRED_API_KEY

    async def get_30y_fixed_rate(self) -> MortgageRateResponse | None:
        url = f"{_FRED_URL}&api_key={self.fred_api_key}"

        for attempt in range(3):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url)
                if response.status_code == 200:
                    for obs in response.json().get("observations", []):
                        v = obs.get("value", "")
                        if v and v != ".":
                            return MortgageRateResponse(
                                value=float(v), date=obs["date"]
                            )
            except Exception:
                pass
            await asyncio.sleep(0.4 + attempt * 0.4)

        return None
