from app.markets.repositories.str_cribs_repository import StrCribsFeeDetailsRepository
from app.markets.schemas.str_cribs import (
    StrCribsFeeDetailsCreateSchema,
    StrCribsFeeDetailsSchema,
    StrCribsFeeDetailsUpdateSchema,
)


class StrCribsFeeDetailsService:
    def __init__(self, repository: StrCribsFeeDetailsRepository):
        self.repository = repository

    async def get_by_id(self, record_id: int) -> StrCribsFeeDetailsSchema | None:
        record = await self.repository.get_by_id(record_id)
        if record is None:
            return None
        return StrCribsFeeDetailsSchema.model_validate(record)

    async def get_all(self) -> list[StrCribsFeeDetailsSchema]:
        records = await self.repository.get_all()
        return [StrCribsFeeDetailsSchema.model_validate(r) for r in records]

    async def create(self, data: StrCribsFeeDetailsCreateSchema) -> StrCribsFeeDetailsSchema:
        record = await self.repository.create(data.model_dump())
        return StrCribsFeeDetailsSchema.model_validate(record)

    async def update(self, record_id: int, data: StrCribsFeeDetailsUpdateSchema) -> StrCribsFeeDetailsSchema | None:
        record = await self.repository.update(record_id, data.model_dump(exclude_unset=True))
        if record is None:
            return None
        return StrCribsFeeDetailsSchema.model_validate(record)

    async def delete(self, record_id: int) -> bool:
        return await self.repository.delete(record_id)
