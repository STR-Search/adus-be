from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.discussions.controller import DiscussionController
from app.core.discussions.interfaces import UserLookup
from app.core.discussions.repository import DiscussionRepository
from app.core.discussions.schemas import CommentDetail, UpdateCommentRequest
from app.core.discussions.service import DiscussionService

# Auth wiring only: app.dependencies provides the current user and the
# UserLookup implementation. Nothing else in discussions imports it.
from app.dependencies import get_current_user, get_user_lookup

router = APIRouter(tags=["discussions"])


def get_discussion_controller(
    db: AsyncSession = Depends(get_db),
    user_lookup: UserLookup = Depends(get_user_lookup),
) -> DiscussionController:
    return DiscussionController(
        DiscussionService(DiscussionRepository(db), user_lookup), db
    )


@router.patch("/comments/{comment_id}", response_model=CommentDetail)
async def edit_comment(
    comment_id: int,
    payload: UpdateCommentRequest,
    controller: DiscussionController = Depends(get_discussion_controller),
    current_user=Depends(get_current_user),
):
    return await controller.edit_comment(comment_id, current_user.id, payload)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: int,
    controller: DiscussionController = Depends(get_discussion_controller),
    current_user=Depends(get_current_user),
):
    await controller.delete_comment(comment_id, current_user.id)
