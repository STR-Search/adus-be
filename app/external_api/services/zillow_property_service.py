import asyncio
from typing import Any

import httpx
import structlog

from app.core.config import get_config
from app.external_api.schemas.zillow_property_details import ZillowPropertyDetails

logger = structlog.get_logger(__name__)

# Scraping upstream is synchronous and can take a while.
_REQUEST_TIMEOUT_SECONDS = 180
_AUTH_TIMEOUT_SECONDS = 30
_MAX_ATTEMPTS = 3


class ZillowPropertyService:
    """Client for the external Zillow property-details API.

    Authenticates against Supabase with a service account (password grant)
    and calls ``POST /api/property-details`` for a property URL. Returns the
    property mapped into the canonical ``ZillowProperty`` dict shape (the same
    shape produced by ``PrepareUwDataService._transform_zillow_property``) so
    it can be persisted on ``uw_details.zillow_property``.
    """

    def __init__(self):
        config = get_config()
        self.api_base = config.ZILLOW_API_BASE.rstrip("/")
        self.supabase_url = config.SUPABASE_URL.rstrip("/")
        self.supabase_anon_key = config.SUPABASE_ANON_KEY
        self.service_email = config.SERVICE_EMAIL
        self.service_password = config.SERVICE_PASSWORD

    def _is_configured(self) -> bool:
        return all(
            (
                self.api_base,
                self.supabase_url,
                self.supabase_anon_key,
                self.service_email,
                self.service_password,
            )
        )

    async def fetch_property_details(self, *, url: str) -> dict[str, Any] | None:
        """Fetch and map a single property by its Zillow URL.

        Returns the canonical ``ZillowProperty`` dict, or ``None`` if the
        client is not configured or the request ultimately fails.
        """
        if not self._is_configured():
            logger.warning(
                "external_api.zillow_property.not_configured",
                detail="Zillow property API env vars are not set — skipping fetch",
            )
            return None

        access_token = await self._get_access_token()
        if access_token is None:
            return None

        details = await self._post_property_details(url=url, access_token=access_token)
        if details is None:
            return None

        return self._to_zillow_property(details, url=url)

    async def _get_access_token(self) -> str | None:
        token_url = f"{self.supabase_url}/auth/v1/token?grant_type=password"
        for attempt in range(_MAX_ATTEMPTS):
            try:
                async with httpx.AsyncClient(timeout=_AUTH_TIMEOUT_SECONDS) as client:
                    response = await client.post(
                        token_url,
                        headers={
                            "apikey": self.supabase_anon_key,
                            "Content-Type": "application/json",
                        },
                        json={
                            "email": self.service_email,
                            "password": self.service_password,
                        },
                    )
                if response.status_code == 200:
                    token = response.json().get("access_token")
                    if token:
                        return token
                logger.warning(
                    "external_api.zillow_property.auth_failed",
                    status_code=response.status_code,
                    attempt=attempt,
                )
            except Exception as exc:
                logger.warning(
                    "external_api.zillow_property.auth_error",
                    error=str(exc),
                    attempt=attempt,
                )
            await asyncio.sleep(0.4 + attempt * 0.4)

        logger.error("external_api.zillow_property.auth_exhausted")
        return None

    async def _post_property_details(
        self, *, url: str, access_token: str
    ) -> ZillowPropertyDetails | None:
        endpoint = f"{self.api_base}/api/property-details"
        for attempt in range(_MAX_ATTEMPTS):
            try:
                async with httpx.AsyncClient(
                    timeout=_REQUEST_TIMEOUT_SECONDS
                ) as client:
                    response = await client.post(
                        endpoint,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                        },
                        json={"url": url},
                    )
                if response.status_code == 200:
                    return self._first_property(response.json(), url=url)
                logger.warning(
                    "external_api.zillow_property.fetch_failed",
                    status_code=response.status_code,
                    url=url,
                    attempt=attempt,
                )
            except Exception as exc:
                logger.warning(
                    "external_api.zillow_property.fetch_error",
                    error=str(exc),
                    url=url,
                    attempt=attempt,
                )
            await asyncio.sleep(0.4 + attempt * 0.4)

        logger.error("external_api.zillow_property.fetch_exhausted", url=url)
        return None

    def _first_property(
        self, body: Any, *, url: str
    ) -> ZillowPropertyDetails | None:
        # The API wraps results as {"data": [ {...} ]}; ``data`` is a list.
        data = body.get("data") if isinstance(body, dict) else body
        if not isinstance(data, list) or not data:
            logger.warning(
                "external_api.zillow_property.empty_response",
                url=url,
            )
            return None
        return ZillowPropertyDetails.model_validate(data[0])

    def _to_zillow_property(
        self, details: ZillowPropertyDetails, *, url: str
    ) -> dict[str, Any]:
        return {
            "id": str(details.zpid) if details.zpid is not None else None,
            "url": url,
            "thumbnail": self._first_photo_url(details.original_photos),
            "price": details.price,
            "address": self._compose_address(details),
            "bedrooms": details.bedrooms,
            "bathrooms": details.bathrooms,
            "area": details.living_area,
            "original_photos": details.original_photos,
            "lot_size_sqft": details.lot_size_sqft,
        }

    @staticmethod
    def _compose_address(details: ZillowPropertyDetails) -> str | None:
        street = details.street_address
        locality = " ".join(
            part for part in (details.state, details.zipcode) if part
        )
        city_line = ", ".join(
            part for part in (details.city, locality or None) if part
        )
        full = ", ".join(part for part in (street, city_line or None) if part)
        return full or None

    @staticmethod
    def _first_photo_url(original_photos: list | None) -> str | None:
        if not original_photos:
            return None
        first = original_photos[0]
        if not isinstance(first, dict):
            return None
        jpegs = first.get("mixedSources", {}).get("jpeg")
        if isinstance(jpegs, list) and jpegs:
            return jpegs[0].get("url")
        return None
