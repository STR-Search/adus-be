from sqlalchemy.exc import IntegrityError

from app.markets.repositories.realtor_repository import RealtorRepository
from app.markets.schemas.realtor import (
    RealtorCreateSchema,
    RealtorSchema,
    RealtorUpdateSchema,
)


class DuplicateRealtorEmailError(Exception):
    """An active realtor already holds this email.

    Realtor identity is the email, matched case- and whitespace-insensitively
    by ``uq_realtors_email_active``. Carries the existing row's id so the
    caller can point the client at the realtor to PATCH (or attach) instead of
    leaving it to guess.
    """

    def __init__(self, email: str, existing_id: int | None):
        super().__init__(f"A realtor with the email '{email}' already exists")
        self.email = email
        self.existing_id = existing_id


class RealtorService:
    def __init__(self, repository: RealtorRepository):
        self.repository = repository

    async def get_by_id(self, record_id: int) -> RealtorSchema | None:
        record = await self.repository.get_by_id(record_id)
        if record is None:
            return None
        return RealtorSchema.model_validate(record)

    async def get_all(self, search: str | None = None) -> list[RealtorSchema]:
        records = await self.repository.get_all(search=search)
        return [RealtorSchema.model_validate(r) for r in records]

    async def create(self, data: RealtorCreateSchema) -> RealtorSchema:
        try:
            record = await self.repository.create(data.model_dump())
        except IntegrityError:
            # The uniqueness check happens here rather than as a pre-flight
            # SELECT so two concurrent creates of the same email can't both
            # pass the check and race to insert.
            await self.repository.db.rollback()
            raise await self._duplicate_error(data.email)
        return RealtorSchema.model_validate(record)

    async def update(
        self, record_id: int, data: RealtorUpdateSchema
    ) -> RealtorSchema | None:
        changes = data.model_dump(exclude_unset=True)
        try:
            record = await self.repository.update(record_id, changes)
        except IntegrityError:
            await self.repository.db.rollback()
            raise await self._duplicate_error(changes.get("email"))
        if record is None:
            return None
        return RealtorSchema.model_validate(record)

    async def delete(self, record_id: int) -> bool:
        return await self.repository.delete(record_id)

    async def _duplicate_error(self, email: str | None) -> DuplicateRealtorEmailError:
        existing = await self.repository.get_active_by_email(email)
        return DuplicateRealtorEmailError(
            email=email or "",
            existing_id=existing.id if existing else None,
        )
