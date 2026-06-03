import uuid

from app.zillow.repositories.scheduled_listing_details_repository import ScheduledListingDetailsRepository
from app.zillow.schemas.scheduled_listing_details import (
    PaginatedScheduledListingDetails,
    ScheduledListingDetailSchema,
)


class ScheduledListingDetailsService:
    def __init__(self, repository: ScheduledListingDetailsRepository):
        self.repository = repository

    async def get_by_zpid(self, zpid: str) -> ScheduledListingDetailSchema | None:
        record = await self.repository.get_by_zpid(zpid)
        if record is None:
            return None
        return ScheduledListingDetailSchema.model_validate(record)

    async def get_all(self, page: int, page_size: int) -> PaginatedScheduledListingDetails:
        items, total, pages = await self.repository.get_all(page=page, page_size=page_size)
        return PaginatedScheduledListingDetails(
            items=[ScheduledListingDetailSchema.model_validate(item) for item in items],
            total=total,
            pages=pages,
        )

    async def get_by_preset_id(
        self, preset_id: uuid.UUID, page: int, page_size: int
    ) -> PaginatedScheduledListingDetails:
        items, total, pages = await self.repository.get_by_preset_id(
            preset_id=preset_id, page=page, page_size=page_size
        )
        return PaginatedScheduledListingDetails(
            items=[ScheduledListingDetailSchema.model_validate(item) for item in items],
            total=total,
            pages=pages,
        )

    async def get_active(self, page: int, page_size: int) -> PaginatedScheduledListingDetails:
        items, total, pages = await self.repository.get_active(page=page, page_size=page_size)
        return PaginatedScheduledListingDetails(
            items=[ScheduledListingDetailSchema.model_validate(item) for item in items],
            total=total,
            pages=pages,
        )
