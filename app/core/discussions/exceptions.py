"""Service-level errors. The controller maps each to an HTTP status.

Body errors (``InvalidBodyError``, ``InvalidMentionError`` → 422) live in
``app.core.discussions.body.errors``.
"""


class DiscussionError(Exception):
    """Base class for discussion errors raised by ``DiscussionService``."""


class CommentNotFoundError(DiscussionError):
    """No such comment, or it is soft-deleted (→ 404)."""

    def __init__(self, comment_id: int):
        super().__init__(f"Comment {comment_id} not found")
        self.comment_id = comment_id


class NotCommentAuthorError(DiscussionError):
    """Only the author may edit or delete a comment (→ 403)."""

    def __init__(self, comment_id: int):
        super().__init__(f"Only the author may modify comment {comment_id}")
        self.comment_id = comment_id


class RepliesNotSupportedError(DiscussionError):
    """``parent_comment_id`` must be null until replies ship (→ 422)."""

    def __init__(self) -> None:
        super().__init__(
            "Replies are not supported yet; parent_comment_id must be null"
        )
