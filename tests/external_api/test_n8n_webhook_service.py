from types import SimpleNamespace

import pytest

from app.external_api.services import n8n_webhook_service as module
from app.external_api.services.n8n_webhook_service import N8nWebhookService


@pytest.fixture
def no_backoff(monkeypatch):
    """Collapse the retry backoff so failure paths don't slow the suite."""

    async def instant(_seconds):
        return None

    monkeypatch.setattr(module.asyncio, "sleep", instant)


@pytest.mark.asyncio
async def test_send_short_circuits_when_disabled():
    service = N8nWebhookService(url="https://example.test/hook", enabled=False)

    assert await service.send(payload={"id": 1}) is False


@pytest.mark.asyncio
async def test_send_short_circuits_when_url_missing():
    service = N8nWebhookService(url="", enabled=True)

    assert await service.send(payload={"id": 1}) is False


@pytest.mark.asyncio
async def test_send_posts_payload_and_returns_true_on_success(monkeypatch):
    service = N8nWebhookService(url="https://example.test/hook", enabled=True)
    posted = {}

    async def fake_post(payload):
        posted.update(payload)
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(service, "_post", fake_post)

    assert await service.send(payload={"id": 42, "deal_status": "present_to_clients"})
    assert posted == {"id": 42, "deal_status": "present_to_clients"}


@pytest.mark.asyncio
async def test_send_returns_false_and_does_not_raise_on_transport_error(
    monkeypatch, no_backoff
):
    service = N8nWebhookService(url="https://example.test/hook", enabled=True)

    async def boom(_payload):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(service, "_post", boom)

    assert await service.send(payload={"id": 1}) is False


@pytest.mark.asyncio
async def test_send_returns_false_when_n8n_rejects(monkeypatch, no_backoff):
    service = N8nWebhookService(url="https://example.test/hook", enabled=True)
    attempts = []

    async def reject(_payload):
        attempts.append(1)
        return SimpleNamespace(status_code=404)

    monkeypatch.setattr(service, "_post", reject)

    assert await service.send(payload={"id": 1}) is False
    assert len(attempts) == module._MAX_ATTEMPTS


def test_falls_back_to_config_when_args_omitted(monkeypatch):
    monkeypatch.setattr(
        module,
        "get_config",
        lambda: SimpleNamespace(
            N8N_WEBHOOK_URL="https://config.test/hook",
            N8N_WEBHOOK_ENABLED=True,
            N8N_WEBHOOK_TIMEOUT_SECONDS=7,
        ),
    )

    service = N8nWebhookService()

    assert service.url == "https://config.test/hook"
    assert service.enabled is True
    assert service.timeout_seconds == 7
