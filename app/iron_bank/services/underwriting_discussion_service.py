"""Comments on underwritings: iron_bank's side of discussions.

Owns the link (``iron_bank.underwriting_threads``) and the lazy creation of
an underwriting's thread; everything else goes through ``DiscussionService``.
Never commits: the controller commits once, so the thread, its link row and
the first comment are created atomically.
"""

from app.core.discussions.enums import SubjectType, ThreadKind
from app.core.discussions.schemas import (
    CommentDetail,
    CommentPage,
    CreateCommentRequest,
)
from app.core.discussions.service import DiscussionService
from app.core.enums import PageSize
from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.repositories.underwriting_thread_repository import (
    UnderwritingThreadRepository,
)


class UnderwritingNotFoundError(Exception):
    def __init__(self, underwriting_id: int):
        super().__init__(f"Underwriting {underwriting_id} not found")
        self.underwriting_id = underwriting_id


class UnderwritingDiscussionService:
    def __init__(
        self,
        underwriting_repository: UnderwritingRepository,
        thread_repository: UnderwritingThreadRepository,
        discussions: DiscussionService,
    ):
        self.underwriting_repository = underwriting_repository
        self.thread_repository = thread_repository
        self.discussions = discussions

    async def list_comments(
        self,
        underwriting_id: int,
        *,
        page: int = 1,
        page_size: PageSize = PageSize.SMALL,
    ) -> CommentPage:
        """Reading never creates a thread: no thread is an empty page."""
        await self._require_underwriting(underwriting_id)
        thread_id = await self.thread_repository.get_thread_id(
            underwriting_id, ThreadKind.GENERAL
        )
        return await self.discussions.list_comments(
            thread_id, page=page, page_size=page_size
        )

    async def create_comment(
        self,
        underwriting_id: int,
        *,
        author_user_id: int,
        payload: CreateCommentRequest,
    ) -> CommentDetail:
        await self._require_underwriting(underwriting_id)
        thread_id = await self._get_or_create_thread(underwriting_id, author_user_id)
        return await self.discussions.create_comment(
            thread_id,
            author_user_id=author_user_id,
            body_version=payload.body_version,
            body=payload.body,
            parent_comment_id=payload.parent_comment_id,
        )

    async def _get_or_create_thread(self, underwriting_id: int, user_id: int) -> int:
        """Design doc §5.1. Does not lock the (wide, hot) underwritings row.

        If the comment then fails validation, the caller does not commit, so
        the new thread and link roll back with it.
        """
        kind = ThreadKind.GENERAL
        existing = await self.thread_repository.get_thread_id(underwriting_id, kind)
        if existing is not None:
            return existing

        thread_id = await self.discussions.create_thread(
            SubjectType.UNDERWRITING, user_id
        )
        if await self.thread_repository.insert_link(underwriting_id, kind, thread_id):
            return thread_id

        # A concurrent first comment linked its thread first: use that one.
        await self.discussions.discard_thread(thread_id)
        winner = await self.thread_repository.get_thread_id(underwriting_id, kind)
        if winner is None:  # the conflicting link vanished (underwriting deleted)
            raise UnderwritingNotFoundError(underwriting_id)
        return winner

    async def _require_underwriting(self, underwriting_id: int) -> None:
        if not await self.underwriting_repository.exists(underwriting_id):
            raise UnderwritingNotFoundError(underwriting_id)
