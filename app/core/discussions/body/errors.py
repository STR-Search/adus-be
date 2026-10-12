from typing import Any


class InvalidBodyError(ValueError):
    """The body failed parsing, a limit, or the emptiness check (maps to 422).

    ``errors`` holds ``{"loc": [...], "msg": str, "type": str}`` entries, with
    ``loc`` rooted at ``"body"`` (or ``"body_version"``).
    """

    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.errors = errors or [
            {"loc": ["body"], "msg": message, "type": "value_error"}
        ]


class InvalidMentionError(ValueError):
    """Mentioned users that do not exist or are soft-deleted (maps to 422)."""

    def __init__(self, user_ids: list[int]):
        super().__init__(f"Invalid mentioned user ids: {user_ids}")
        self.user_ids = user_ids
