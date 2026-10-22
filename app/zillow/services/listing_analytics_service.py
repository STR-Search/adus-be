from datetime import date

from app.zillow.repositories.listing_analytics_repository import (
    ListingAnalyticsRepository,
)
from app.zillow.schemas.listing_analytics import HomeStatusBreakdown, HomeStatusCount


class ListingAnalyticsService:
    def __init__(self, repository: ListingAnalyticsRepository):
        self.repository = repository

    async def get_home_status_breakdown(
        self,
        *,
        market_id: int | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
    ) -> HomeStatusBreakdown:
        rows = await self.repository.count_by_home_status(
            market_id=market_id,
            created_from=created_from,
            created_to=created_to,
        )
        # Some scraped rows carry "" rather than NULL; both mean "unknown".
        counts: dict[str | None, int] = {}
        for status, count in rows:
            key = status or None
            counts[key] = counts.get(key, 0) + count
        return HomeStatusBreakdown(
            total=sum(counts.values()),
            statuses=[
                HomeStatusCount(home_status=status, count=count)
                for status, count in sorted(counts.items(), key=lambda item: -item[1])
            ],
        )
