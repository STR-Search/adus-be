import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.query_filters import date_range_conditions, numeric_range_conditions
from app.iron_bank.enums import DealStatus, UnderwritingSource
from app.iron_bank.models import Underwriting
from app.iron_bank.repositories.underwriting_analytics_repository import (
    status_in,
    underwriting_filter_conditions,
)
from app.iron_bank.repositories.underwriting_repository import (
    NOT_PENDING_HOME_STATUSES,
)
from app.iron_bank.schemas.underwriting_analytics import UnderwritingAnalyticsFilters
from app.zillow.models.scheduled_listing_details import ScheduledListingDetail
from app.zillow.models.scheduled_listings import ScheduledListing
from app.zillow.models.scheduled_presets import ScheduledPreset

_SECONDS_PER_DAY = 86_400


def off_market_condition():
    """The listing is off the market: the same rule ``property_pending`` uses.

    ``COALESCE`` makes a missing status count as off the market, because a bare
    ``NULL NOT IN (...)`` is NULL, not true.
    """
    return func.coalesce(ScheduledListing.home_status, "").not_in(
        NOT_PENDING_HOME_STATUSES
    )


class PipelineAnalyticsRepository:
    """Read-only queries that join zillow listings to iron_bank underwritings."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def coverage(
        self,
        *,
        source: Sequence[UnderwritingSource],
        group_by_preset: bool,
        market_id: int | None = None,
        preset_id: uuid.UUID | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
    ) -> list[tuple]:
        """``(preset_id, name, listings, underwritten, median_days)`` rows.

        Each listing is matched to its earliest underwriting; the median is of
        days from the listing's first-seen time to that underwriting. Without
        ``group_by_preset``, one overall row with ``None`` preset columns.

        ``market_id`` narrows listings to that market's presets: a listing that
        was never underwritten has no deal market, so its preset's market is
        the only one it has (the same rule as the listing endpoints).
        """
        first_underwriting = (
            select(
                Underwriting.zpid.label("zpid"),
                func.min(Underwriting.deal_added).label("first_added"),
            )
            .where(
                Underwriting.zpid.is_not(None),
                Underwriting.source.in_([s.value for s in source]),
            )
            .group_by(Underwriting.zpid)
            .subquery()
        )
        days = (
            func.extract(
                "epoch", first_underwriting.c.first_added - ScheduledListing.created_at
            )
            / _SECONDS_PER_DAY
        )
        measures = (
            func.count().label("listings"),
            func.count(first_underwriting.c.zpid).label("underwritten"),
            func.percentile_cont(0.5).within_group(days).label("median_days"),
        )
        conditions = date_range_conditions(
            ScheduledListing.created_at, created_from, created_to
        )
        if market_id is not None:
            # A subquery rather than a join, so it composes with the preset
            # join the per-preset rows add.
            conditions.append(
                ScheduledListing.preset_id.in_(
                    select(ScheduledPreset.id).where(
                        ScheduledPreset.market_id == market_id
                    )
                )
            )
        if preset_id is not None:
            conditions.append(ScheduledListing.preset_id == preset_id)

        if group_by_preset:
            query = (
                select(ScheduledListing.preset_id, ScheduledPreset.name, *measures)
                .join(ScheduledPreset, ScheduledPreset.id == ScheduledListing.preset_id)
                .outerjoin(
                    first_underwriting,
                    first_underwriting.c.zpid == ScheduledListing.zpid,
                )
                .where(*conditions)
                .group_by(ScheduledListing.preset_id, ScheduledPreset.name)
            )
        else:
            query = (
                select(*measures)
                .select_from(ScheduledListing)
                .outerjoin(
                    first_underwriting,
                    first_underwriting.c.zpid == ScheduledListing.zpid,
                )
                .where(*conditions)
            )
        result = await self.db.execute(query)
        rows = [tuple(row) for row in result.all()]
        return rows if group_by_preset else [(None, None, *row) for row in rows]

    async def count_off_market(
        self, filters: UnderwritingAnalyticsFilters
    ) -> list[tuple[str | None, str | None, int]]:
        """``(deal_status, home_status, count)`` for underwritings now off the market."""
        query = (
            select(Underwriting.deal_status, ScheduledListing.home_status, func.count())
            .join(ScheduledListing, ScheduledListing.zpid == Underwriting.zpid)
            .where(*underwriting_filter_conditions(filters), off_market_condition())
            .group_by(Underwriting.deal_status, ScheduledListing.home_status)
        )
        result = await self.db.execute(query)
        return [(status, home, count) for status, home, count in result.all()]

    async def count_with_status(
        self, filters: UnderwritingAnalyticsFilters, statuses: Sequence[DealStatus]
    ) -> int:
        """Underwritings in ``statuses``, on or off the market (a denominator)."""
        query = select(func.count()).where(
            *underwriting_filter_conditions(filters), status_in(statuses)
        )
        return (await self.db.execute(query)).scalar_one()

    async def price_drops(
        self,
        filters: UnderwritingAnalyticsFilters,
        *,
        statuses: Sequence[DealStatus],
        changed_from: date | None = None,
        changed_to: date | None = None,
    ) -> tuple[list[tuple[str, int]], float | None, int]:
        """Deals in ``statuses`` whose listing's latest price change is a drop.

        Returns per-status counts, plus the median drop as a positive fraction
        of the price before the drop (0.05 = cut by 5%) and how many deals that
        median is based on. Zillow stores a drop as a negative ``price_change``
        and ``price`` is the price after it (checked against dev data).
        """
        previous_price = (
            ScheduledListingDetail.price - ScheduledListingDetail.price_change
        )
        drop_pct = func.abs(ScheduledListingDetail.price_change) / func.nullif(
            previous_price, 0
        )
        conditions = [
            *underwriting_filter_conditions(filters),
            status_in(statuses),
            ScheduledListingDetail.price_change < 0,
            *numeric_range_conditions(
                ScheduledListingDetail.price_change_date, changed_from, changed_to
            ),
        ]
        join_on = ScheduledListingDetail.zpid == Underwriting.zpid
        per_status = (
            select(Underwriting.deal_status, func.count())
            .join(ScheduledListingDetail, join_on)
            .where(*conditions)
            .group_by(Underwriting.deal_status)
        )
        median = (
            select(
                func.percentile_cont(0.5).within_group(drop_pct), func.count(drop_pct)
            )
            .select_from(Underwriting)
            .join(ScheduledListingDetail, join_on)
            .where(*conditions)
        )
        rows = [
            (status, count)
            for status, count in (await self.db.execute(per_status)).all()
        ]
        median_value, sample_size = (await self.db.execute(median)).one()
        return rows, median_value, sample_size
