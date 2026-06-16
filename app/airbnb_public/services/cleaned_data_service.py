from typing import Protocol

from app.airbnb_public.models.cleaned_data import CleanedData
from app.airbnb_public.schemas.cleaned_data import CleanedDataSchema


class CleanedDataReader(Protocol):
    async def get_by_id(self, cleaned_data_id: int) -> CleanedData | None: ...


class CleanedDataService:
    def __init__(self, repository: CleanedDataReader):
        self.repository = repository

    async def get_by_id(self, cleaned_data_id: int) -> CleanedDataSchema | None:
        item = await self.repository.get_by_id(cleaned_data_id)
        if item is None:
            return None
        return CleanedDataSchema.model_validate(item)
