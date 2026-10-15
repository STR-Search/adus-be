from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.discussions.body.errors import InvalidBodyError, InvalidMentionError
from app.core.discussions.exceptions import (
    CommentNotFoundError,
    NotCommentAuthorError,
    RepliesNotSupportedError,
)
from app.core.discussions.schemas import CommentDetail, UpdateCommentRequest
from app.core.discussions.service import DiscussionService
from app.core.logger import logger


def discussion_http_error(exc: Exception) -> HTTPException | None:
    """Map a discussion error to its HTTP response, or ``None`` if not one.

    Public so domain controllers (e.g. iron_bank's comment routes) map the
    same errors the same way. 422 details use FastAPI's ``loc``/``msg``/
    ``type`` list shape.
    """
    if isinstance(exc, CommentNotFoundError):
        return HTTPException(status_code=404, detail="Comment not found")
    if isinstance(exc, NotCommentAuthorError):
        return HTTPException(
            status_code=403, detail="Only the author can modify this comment"
        )
    if isinstance(exc, InvalidBodyError):
        return HTTPException(status_code=422, detail=exc.errors)
    if isinstance(exc, InvalidMentionError):
        return HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body"],
                    "msg": "Mentioned users do not exist or are deleted",
                    "type": "invalid_mention",
                    "ctx": {"user_ids": exc.user_ids},
                }
            ],
        )
    if isinstance(exc, RepliesNotSupportedError):
        return HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["parent_comment_id"],
                    "msg": str(exc),
                    "type": "replies_not_supported",
                }
            ],
        )
    return None


class DiscussionController:
    """Routes owned by discussions (``/comments/{id}``).

    Unlike other controllers, this one commits: ``DiscussionService`` never
    does, so the caller owns the transaction (see the design doc §5).
    """

    def __init__(self, service: DiscussionService, db: AsyncSession):
        self.service = service
        self.db = db

    async def edit_comment(
        self, comment_id: int, user_id: int, payload: UpdateCommentRequest
    ) -> CommentDetail:
        try:
            detail = await self.service.edit_comment(
                comment_id,
                user_id=user_id,
                body_version=payload.body_version,
                body=payload.body,
            )
            await self.db.commit()
            return detail
        except Exception as e:
            raise self._http_error(e, "edit", comment_id) from e

    async def delete_comment(self, comment_id: int, user_id: int) -> None:
        try:
            await self.service.delete_comment(comment_id, user_id=user_id)
            await self.db.commit()
        except Exception as e:
            raise self._http_error(e, "delete", comment_id) from e

    @staticmethod
    def _http_error(exc: Exception, action: str, comment_id: int) -> HTTPException:
        # The session is rolled back when get_db closes it.
        mapped = discussion_http_error(exc)
        if mapped is not None:
            return mapped
        logger.error(
            f"discussions.comment.{action}.error",
            comment_id=comment_id,
            error=str(exc),
        )
        return HTTPException(status_code=500, detail=f"Failed to {action} comment")
