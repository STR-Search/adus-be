from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.discussions.controller import discussion_http_error
from app.core.discussions.schemas import (
    CommentDetail,
    CommentPage,
    CreateCommentRequest,
)
from app.core.enums import PageSize
from app.core.logger import logger
from app.iron_bank.services.underwriting_discussion_service import (
    UnderwritingDiscussionService,
    UnderwritingNotFoundError,
)


class UnderwritingCommentController:
    """``/underwritings/{id}/comments``. Commits on create, because the
    services never do (see docs/underwriting_discussions.md §5)."""

    def __init__(self, service: UnderwritingDiscussionService, db: AsyncSession):
        self.service = service
        self.db = db

    async def list_comments(
        self, underwriting_id: int, *, page: int, page_size: PageSize
    ) -> CommentPage:
        try:
            return await self.service.list_comments(
                underwriting_id, page=page, page_size=page_size
            )
        except Exception as e:
            raise self._http_error(e, "list", underwriting_id) from e

    async def create_comment(
        self,
        underwriting_id: int,
        *,
        author_user_id: int,
        payload: CreateCommentRequest,
    ) -> CommentDetail:
        try:
            detail = await self.service.create_comment(
                underwriting_id, author_user_id=author_user_id, payload=payload
            )
            await self.db.commit()
            return detail
        except Exception as e:
            raise self._http_error(e, "create", underwriting_id) from e

    @staticmethod
    def _http_error(exc: Exception, action: str, underwriting_id: int) -> HTTPException:
        # On any error nothing is committed; get_db's session close rolls back
        # a lazily created thread and link along with the comment.
        if isinstance(exc, UnderwritingNotFoundError):
            return HTTPException(status_code=404, detail="Underwriting not found")
        mapped = discussion_http_error(exc)
        if mapped is not None:
            return mapped
        logger.error(
            f"iron_bank.underwriting_comments.{action}.error",
            underwriting_id=underwriting_id,
            error=str(exc),
        )
        detail = (
            "Failed to list comments"
            if action == "list"
            else "Failed to create comment"
        )
        return HTTPException(status_code=500, detail=detail)
