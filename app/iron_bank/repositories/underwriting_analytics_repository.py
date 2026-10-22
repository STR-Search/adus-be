from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.iron_bank.models import Underwriting
from app.iron_bank.repositories.underwriting_repository import _date_range_conditions


class UnderwritingAnalyticsRepository:
    """Read-only aggregate queries over ``iron_bank.underwritings``."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def count_by_deal_status(
        self,
        *,
        market_id: int | None = None,
        analyst_id: int | None = None,
        added_from: date | None = None,
        added_to: date | None = None,
    ) -> list[tuple[str | None, int]]:
        conditions = _date_range_conditions(Underwriting.deal_added, added_from, added_to)
        if market_id is not None:
            conditions.append(Underwriting.market_id == market_id)
        if analyst_id is not None:
            conditions.append(Underwriting.analyst_id == analyst_id)

        query = (
            select(Underwriting.deal_status, func.count())
            .where(*conditions)
            .group_by(Underwriting.deal_status)
        )
        result = await self.db.execute(query)
        return [(status, count) for status, count in result.all()]
