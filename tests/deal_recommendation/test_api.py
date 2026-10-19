import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deal_recommendation.router import (
    get_conversation_controller,
    get_run_manager,
    router,
)
from app.deal_recommendation.services.run_manager import ConversationBusy, format_sse
from app.dependencies import get_current_user

CONV_ID = uuid.uuid4()
NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)


class FakeController:
    def __init__(self):
        self.created = []

    async def create(self, *, title, user_id):
        self.created.append((title, user_id))
        return {"id": CONV_ID, "title": title, "created_at": NOW, "updated_at": NOW}

    async def list(self):
        return {"items": [{"id": CONV_ID, "title": "Rav & Anna", "created_at": NOW, "updated_at": NOW}]}

    async def get(self, conversation_id):
        if conversation_id != CONV_ID:
            return None
        return {"id": CONV_ID, "title": "Rav & Anna", "turns": []}

    async def exists(self, conversation_id):
        return conversation_id == CONV_ID

    async def trace(self, run_id):
        return None


class FakeRunManager:
    def __init__(self, busy=False):
        self.busy = busy
        self.started = []

    async def start(self, *, conversation_id, text, user_id, pool_override=None):
        if self.busy:
            raise ConversationBusy()
        self.started.append((conversation_id, text, user_id))

        async def gen():
            yield format_sse("run_started", {"run_id": "r1"})
            yield format_sse("run_finished", {"status": "succeeded"})

        return gen()


def build_client(run_manager=None, controller=None):
    app = FastAPI()
    app.include_router(router)
    controller = controller or FakeController()
    app.dependency_overrides[get_conversation_controller] = lambda: controller
    app.dependency_overrides[get_run_manager] = lambda: run_manager or FakeRunManager()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=99)
    return TestClient(app), controller


def test_create_and_list_conversations():
    client, controller = build_client()
    response = client.post("/deal-recommendation/conversations", json={"title": "Rav & Anna"})
    assert response.status_code == 201
    assert response.json()["id"] == str(CONV_ID)
    assert controller.created == [("Rav & Anna", 99)]
    listed = client.get("/deal-recommendation/conversations").json()
    assert listed["items"][0]["title"] == "Rav & Anna"


def test_create_without_title():
    client, controller = build_client()
    assert client.post("/deal-recommendation/conversations", json={}).status_code == 201
    assert controller.created == [(None, 99)]


def test_get_missing_conversation_404():
    client, _ = build_client()
    assert client.get(f"/deal-recommendation/conversations/{uuid.uuid4()}").status_code == 404


def test_post_message_streams_sse_events():
    manager = FakeRunManager()
    client, _ = build_client(run_manager=manager)
    response = client.post(
        f"/deal-recommendation/conversations/{CONV_ID}/messages", json={"text": "notes"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: run_started" in response.text
    assert manager.started == [(CONV_ID, "notes", 99)]


def test_post_message_to_missing_conversation_404():
    client, _ = build_client()
    response = client.post(
        f"/deal-recommendation/conversations/{uuid.uuid4()}/messages", json={"text": "x"}
    )
    assert response.status_code == 404


def test_post_message_when_busy_returns_409():
    client, _ = build_client(run_manager=FakeRunManager(busy=True))
    response = client.post(
        f"/deal-recommendation/conversations/{CONV_ID}/messages", json={"text": "notes"}
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "A run is already in progress for this conversation."


def test_message_text_validation():
    client, _ = build_client()
    url = f"/deal-recommendation/conversations/{CONV_ID}/messages"
    assert client.post(url, json={"text": ""}).status_code == 422
    assert client.post(url, json={"text": "x" * 50001}).status_code == 422


def test_trace_404():
    client, _ = build_client()
    assert client.get(f"/deal-recommendation/runs/{uuid.uuid4()}/trace").status_code == 404
