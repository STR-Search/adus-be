import asyncio
from typing import Any

import httpx
import structlog

from app.core.config import get_config

logger = structlog.get_logger(__name__)

# One retry, not the three used by the other clients in this package. Those
# fetch data we need; this one announces an event that already happened. A
# single retry covers a transient connection blip, while every extra attempt is
# another chance to deliver twice if n8n accepted and the response was lost.
_MAX_ATTEMPTS = 2


class N8nWebhookService:
    """Fire-and-forget client for the n8n automation webhook.

    Never raises: the DB write it reports has already committed, so a failure
    here must not surface to the caller — an n8n outage cannot be allowed to
    break a status change. Returns whether n8n accepted the event, for logging
    and tests.
    """

    def __init__(
        self,
        url: str | None = None,
        enabled: bool | None = None,
        timeout_seconds: int | None = None,
    ):
        config = get_config()
        self.url = config.N8N_WEBHOOK_URL if url is None else url
        self.enabled = config.N8N_WEBHOOK_ENABLED if enabled is None else enabled
        self.timeout_seconds = (
            config.N8N_WEBHOOK_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )

    async def send(self, *, payload: dict[str, Any]) -> bool:
        if not self.enabled:
            logger.debug("external_api.n8n_webhook.disabled")
            return False
        if not self.url:
            logger.warning(
                "external_api.n8n_webhook.not_configured",
                detail="N8N_WEBHOOK_ENABLED is true but N8N_WEBHOOK_URL is empty",
            )
            return False

        underwriting_id = payload.get("id")
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = await self._post(payload)
                if 200 <= response.status_code < 300:
                    logger.info(
                        "external_api.n8n_webhook.sent",
                        status_code=response.status_code,
                        underwriting_id=underwriting_id,
                    )
                    return True
                logger.warning(
                    "external_api.n8n_webhook.rejected",
                    status_code=response.status_code,
                    underwriting_id=underwriting_id,
                    attempt=attempt,
                )
            except Exception as exc:
                logger.warning(
                    "external_api.n8n_webhook.error",
                    error=str(exc),
                    underwriting_id=underwriting_id,
                    attempt=attempt,
                )
            await asyncio.sleep(0.4 + attempt * 0.4)

        logger.error(
            "external_api.n8n_webhook.exhausted",
            underwriting_id=underwriting_id,
        )
        return False

    def _headers(self) -> dict[str, str]:
        """Outbound headers.

        Auth seam: when the n8n workflow starts requiring a shared secret, add
        ``N8N_WEBHOOK_TOKEN`` to config and return it here. No call site changes.
        """
        return {"Content-Type": "application/json"}

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        """Isolated so tests can replace the network call without patching httpx."""
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            return await client.post(self.url, json=payload, headers=self._headers())
