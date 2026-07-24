from app.markets.repositories.realtor_repository import RealtorRepository
from app.markets.schemas.realtor import (
    RealtorCreateSchema,
    RealtorSchema,
    RealtorUpdateSchema,
)


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
        record = await self.repository.create(data.model_dump())
        return RealtorSchema.model_validate(record)

    async def update(self, record_id: int, data: RealtorUpdateSchema) -> RealtorSchema | None:
        record = await self.repository.update(record_id, data.model_dump(exclude_unset=True))
        if record is None:
            return None
        return RealtorSchema.model_validate(record)

    async def delete(self, record_id: int) -> bool:
        return await self.repository.delete(record_id)
