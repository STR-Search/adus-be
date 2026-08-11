from app.users.repositories.user_repository import UserRepository
from app.users.schemas.user import UserDetail, UserListResult, UserSummary


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    async def get_all(self, *, detailed: bool = False) -> UserListResult:
        """Every non-deleted user. Unpaginated — the table is small enough that
        callers (assignee pickers) want the whole set in one request."""
        users = await self.repository.get_all()
        schema = UserDetail if detailed else UserSummary
        return UserListResult(
            items=[schema.model_validate(user) for user in users],
            total=len(users),
        )
