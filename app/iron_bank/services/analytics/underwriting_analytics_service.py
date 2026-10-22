from datetime import date

from app.iron_bank.repositories.underwriting_analytics_repository import (
    UnderwritingAnalyticsRepository,
)
from app.iron_bank.schemas.underwriting_analytics import (
    DealStatusBreakdown,
    DealStatusCount,
)
from app.iron_bank.services.deal_status_service import STATUS_OPTIONS

_LABELS: dict[str, str] = {status.value: label for status, label, _ in STATUS_OPTIONS}
_SORT_ORDER: dict[str, int] = {status.value: order for status, _, order in STATUS_OPTIONS}


class UnderwritingAnalyticsService:
    def __init__(self, repository: UnderwritingAnalyticsRepository):
        self.repository = repository

    async def get_deal_status_breakdown(
        self,
        *,
        market_id: int | None = None,
        analyst_id: int | None = None,
        added_from: date | None = None,
        added_to: date | None = None,
    ) -> DealStatusBreakdown:
        rows = await self.repository.count_by_deal_status(
            market_id=market_id,
            analyst_id=analyst_id,
            added_from=added_from,
            added_to=added_to,
        )
        # Known statuses in workflow order; unknown legacy values and unset
        # statuses go last so they're visible rather than silently dropped.
        rows.sort(
            key=lambda row: (
                row[0] is None,
                _SORT_ORDER.get(row[0], len(_SORT_ORDER) + 1),
                row[0] or "",
            )
        )
        return DealStatusBreakdown(
            total=sum(count for _, count in rows),
            statuses=[
                DealStatusCount(
                    key=status,
                    label=_LABELS.get(status, status) if status else "No Status",
                    count=count,
                )
                for status, count in rows
            ],
        )
