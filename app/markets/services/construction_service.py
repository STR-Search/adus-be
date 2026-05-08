from app.markets.repositories.construction_repository import (
    ConstructionAmenitiesRepository,
    ConstructionRemodelingRepository,
)
from app.markets.schemas.construction import (
    ConstructionCostsAmenitiesCreateSchema,
    ConstructionCostsAmenitiesSchema,
    ConstructionCostsAmenitiesUpdateSchema,
    ConstructionCostsRemodelingCreateSchema,
    ConstructionCostsRemodelingSchema,
    ConstructionCostsRemodelingUpdateSchema,
)


class ConstructionAmenitiesService:
    def __init__(self, repository: ConstructionAmenitiesRepository):
        self.repository = repository

    async def get_by_id(self, record_id: int) -> ConstructionCostsAmenitiesSchema | None:
        record = await self.repository.get_by_id(record_id)
        if record is None:
            return None
        return ConstructionCostsAmenitiesSchema.model_validate(record)

    async def get_all(
        self,
        location: str | None = None,
        search: str | None = None,
    ) -> list[ConstructionCostsAmenitiesSchema]:
        records = await self.repository.get_all(location=location, search=search)
        return [ConstructionCostsAmenitiesSchema.model_validate(r) for r in records]

    async def create(self, data: ConstructionCostsAmenitiesCreateSchema) -> ConstructionCostsAmenitiesSchema:
        record = await self.repository.create(data.model_dump())
        return ConstructionCostsAmenitiesSchema.model_validate(record)

    async def update(self, record_id: int, data: ConstructionCostsAmenitiesUpdateSchema) -> ConstructionCostsAmenitiesSchema | None:
        record = await self.repository.update(record_id, data.model_dump(exclude_unset=True))
        if record is None:
            return None
        return ConstructionCostsAmenitiesSchema.model_validate(record)

    async def delete(self, record_id: int) -> bool:
        return await self.repository.delete(record_id)


class ConstructionRemodelingService:
    def __init__(self, repository: ConstructionRemodelingRepository):
        self.repository = repository

    async def get_by_id(self, record_id: int) -> ConstructionCostsRemodelingSchema | None:
        record = await self.repository.get_by_id(record_id)
        if record is None:
            return None
        return ConstructionCostsRemodelingSchema.model_validate(record)

    async def get_all(
        self,
        location: str | None = None,
        search: str | None = None,
    ) -> list[ConstructionCostsRemodelingSchema]:
        records = await self.repository.get_all(location=location, search=search)
        return [ConstructionCostsRemodelingSchema.model_validate(r) for r in records]

    async def create(self, data: ConstructionCostsRemodelingCreateSchema) -> ConstructionCostsRemodelingSchema:
        record = await self.repository.create(data.model_dump())
        return ConstructionCostsRemodelingSchema.model_validate(record)

    async def update(self, record_id: int, data: ConstructionCostsRemodelingUpdateSchema) -> ConstructionCostsRemodelingSchema | None:
        record = await self.repository.update(record_id, data.model_dump(exclude_unset=True))
        if record is None:
            return None
        return ConstructionCostsRemodelingSchema.model_validate(record)

    async def delete(self, record_id: int) -> bool:
        return await self.repository.delete(record_id)
