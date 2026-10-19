from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

import app.deal_recommendation.models  # noqa: F401 — registers the tables
from app.core.database import get_db
from app.dependencies import get_current_user
from app.deal_recommendation.controllers.conversation_controller import (
    ConversationController,
)
from app.deal_recommendation.repositories.conversation_repository import (
    ConversationRepository,
)
from app.deal_recommendation.repositories.recommendation_repository import (
    RecommendationRepository,
)
from app.deal_recommendation.repositories.run_repository import RunRepository
from app.deal_recommendation.schemas.api import (
    ConversationDetail,
    ConversationListResult,
    ConversationSummary,
    CreateConversationPayload,
    PostMessagePayload,
    RunTrace,
)
from app.deal_recommendation.services.conversation_service import ConversationService
from app.deal_recommendation.services.run_manager import (
    ConversationBusy,
    RunManager,
    run_manager,
)

router = APIRouter(prefix="/deal-recommendation", tags=["deal_recommendation"])

BUSY_DETAIL = "A run is already in progress for this conversation."


def get_conversation_controller(db: AsyncSession = Depends(get_db)) -> ConversationController:
    service = ConversationService(
        ConversationRepository(db), RunRepository(db), RecommendationRepository(db)
    )
    return ConversationController(service, db)


def get_run_manager() -> RunManager:
    return run_manager


@router.post(
    "/conversations",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: CreateConversationPayload,
    controller: ConversationController = Depends(get_conversation_controller),
    current_user=Depends(get_current_user),
):
    return await controller.create(
        title=payload.title, user_id=getattr(current_user, "id", None)
    )


@router.get("/conversations", response_model=ConversationListResult)
async def list_conversations(
    controller: ConversationController = Depends(get_conversation_controller),
):
    return await controller.list()


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    controller: ConversationController = Depends(get_conversation_controller),
):
    detail = await controller.get(conversation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return detail


@router.post("/conversations/{conversation_id}/messages")
async def post_message(
    conversation_id: UUID,
    payload: PostMessagePayload,
    controller: ConversationController = Depends(get_conversation_controller),
    manager: RunManager = Depends(get_run_manager),
    current_user=Depends(get_current_user),
):
    """Run the agent on a new message; streams its events as Server-Sent Events."""
    if not await controller.exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    try:
        stream = await manager.start(
            conversation_id=conversation_id,
            text=payload.text,
            user_id=getattr(current_user, "id", None),
        )
    except ConversationBusy:
        raise HTTPException(status_code=409, detail=BUSY_DETAIL)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/trace", response_model=RunTrace)
async def get_run_trace(
    run_id: UUID,
    controller: ConversationController = Depends(get_conversation_controller),
):
    trace = await controller.trace(run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return trace
