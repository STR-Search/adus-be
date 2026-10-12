from collections.abc import Collection
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class UserRef:
    """The user fields discussions needs: mention validation and display names."""

    id: int
    first_name: str | None
    last_name: str | None
    email: str | None
    is_deleted: bool


class UserLookup(Protocol):
    """Resolves user ids without discussions importing the users domain.

    Implemented in ``app/dependencies.py``. Must return soft-deleted users too
    (with ``is_deleted=True``) so callers can tell "deleted" from "unknown".
    Ids that do not exist are absent from the result.
    """

    async def get_users(self, user_ids: Collection[int]) -> dict[int, UserRef]: ...
