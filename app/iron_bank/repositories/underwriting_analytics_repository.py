from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, case, cast, distinct, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics.schemas import Granularity
from app.core.query_filters import date_range_conditions
from app.iron_bank.enums import DealStatus
from app.iron_bank.models import Job, Underwriting
from app.iron_bank.schemas.underwriting_analytics import UnderwritingAnalyticsFilters

# (key, lower inclusive, upper exclusive); None = open end.
PriceBandBounds = Sequence[tuple[str, Decimal | None, Decimal | None]]


def underwriting_filter_conditions(filters: UnderwritingAnalyticsFilters) -> list:
    """WHERE conditions for the population ``filters`` describes.

    Public so the cross-domain analytics repositories narrow underwritings
    exactly the way the single-domain ones do.
    """
    conditions = date_range_conditions(
        Underwriting.deal_added, filters.added_from, filters.added_to
    )
    conditions.append(Underwriting.source.in_([s.value for s in filters.source]))
    if filters.market_id is not None:
        conditions.append(Underwriting.market_id == filters.market_id)
    if filters.analyst_id is not None:
        conditions.append(Underwriting.analyst_id == filters.analyst_id)
    if filters.deal_status is not None:
        conditions.append(status_in(filters.deal_status))
    return conditions


def status_in(statuses: Sequence[DealStatus]):
    return Underwriting.deal_status.in_([s.value for s in statuses])


def period_column(column, granularity: Granularity):
    """``column`` truncated to its UTC day/week (weeks start Monday), as a date."""
    return cast(
        func.date_trunc(granularity.value, func.timezone("UTC", column)), Date
    ).label("period_start")


class UnderwritingAnalyticsRepository:
    """Read-only aggregate queries over ``iron_bank.underwritings`` and ``iron_bank.jobs``."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def count_by_deal_status(
        self, filters: UnderwritingAnalyticsFilters
    ) -> list[tuple[str | None, int]]:
        query = (
            select(Underwriting.deal_status, func.count())
            .where(*underwriting_filter_conditions(filters))
            .group_by(Underwriting.deal_status)
        )
        result = await self.db.execute(query)
        return [(status, count) for status, count in result.all()]

    async def template_progress(
        self, filters: UnderwritingAnalyticsFilters, granularity: Granularity
    ) -> list[tuple[date, int, int]]:
        period = period_column(Underwriting.deal_added, granularity)
        past_template = func.count().filter(
            Underwriting.deal_status.is_not(None),
            Underwriting.deal_status != DealStatus.TEMPLATE_GENERATED.value,
        )
        query = (
            select(period, func.count(), past_template)
            .where(*underwriting_filter_conditions(filters))
            .where(Underwriting.deal_added.is_not(None))
            .group_by(period)
        )
        result = await self.db.execute(query)
        return [(start, created, past) for start, created, past in result.all()]

    async def count_by_market_and_status(
        self, filters: UnderwritingAnalyticsFilters
    ) -> list[tuple[int | None, str | None, int]]:
        query = (
            select(Underwriting.market_id, Underwriting.deal_status, func.count())
            .where(*underwriting_filter_conditions(filters))
            .group_by(Underwriting.market_id, Underwriting.deal_status)
        )
        result = await self.db.execute(query)
        return [(market, status, count) for market, status, count in result.all()]

    async def count_by_price_band_and_status(
        self, filters: UnderwritingAnalyticsFilters, bands: PriceBandBounds
    ) -> list[tuple[str | None, str | None, int]]:
        band = _price_band_case(bands)
        query = (
            select(band, Underwriting.deal_status, func.count())
            .where(*underwriting_filter_conditions(filters))
            .group_by(band, Underwriting.deal_status)
        )
        result = await self.db.execute(query)
        return [(key, status, count) for key, status, count in result.all()]

    async def quality_medians(
        self, filters: UnderwritingAnalyticsFilters, statuses: Sequence[DealStatus]
    ) -> dict[str, float | int | None]:
        """Deal count plus median and non-null count per quality column."""
        columns = {
            "cash_on_cash": Underwriting.m_cash_on_cash,
            "deal_score": Underwriting.deal_score,
            "total_oop": Underwriting.total_oop,
        }
        selected = [func.count().label("deals")]
        for name, column in columns.items():
            selected.append(
                func.percentile_cont(0.5).within_group(column).label(f"{name}_median")
            )
            selected.append(func.count(column).label(f"{name}_count"))
        query = select(*selected).where(
            *underwriting_filter_conditions(filters), status_in(statuses)
        )
        result = await self.db.execute(query)
        return dict(result.one()._mapping)

    async def count_tags(
        self, filters: UnderwritingAnalyticsFilters, field: str, *, multi_select: bool
    ) -> tuple[int, list[tuple[str | None, int]]]:
        """``(deals, [(slug, deals carrying it)])`` for one tag column.

        The ``None`` slug counts deals with the tag unset (or, for multi-select,
        an empty list).
        """
        column = getattr(Underwriting, field)
        conditions = underwriting_filter_conditions(filters)
        if multi_select:
            untagged = or_(column.is_(None), func.cardinality(column) == 0)
            totals = select(func.count(), func.count().filter(untagged)).where(
                *conditions
            )
            tags = (
                select(Underwriting.id, func.unnest(column).label("slug"))
                .where(*conditions)
                .subquery()
            )
            per_tag = select(tags.c.slug, func.count(distinct(tags.c.id))).group_by(
                tags.c.slug
            )
            deals, unset = (await self.db.execute(totals)).one()
            rows = [
                (slug, count) for slug, count in (await self.db.execute(per_tag)).all()
            ]
            if unset:
                rows.append((None, unset))
            return deals, rows

        per_tag = select(column, func.count()).where(*conditions).group_by(column)
        rows = [(slug, count) for slug, count in (await self.db.execute(per_tag)).all()]
        return sum(count for _, count in rows), rows

    async def duplicates(
        self, filters: UnderwritingAnalyticsFilters
    ) -> tuple[int, int, int]:
        conditions = underwriting_filter_conditions(filters)
        repeated = (
            select(func.count().label("rows"))
            .where(*conditions, Underwriting.zpid.is_not(None))
            .group_by(Underwriting.zpid)
            .having(func.count(distinct(Underwriting.series_id)) > 1)
            .subquery()
        )
        repeated_query = select(
            func.count(), func.coalesce(func.sum(repeated.c.rows), 0)
        ).select_from(repeated)
        copies_query = select(func.count()).where(
            *conditions, Underwriting.copied_from_id.is_not(None)
        )
        properties, rows = (await self.db.execute(repeated_query)).one()
        copies = (await self.db.execute(copies_query)).scalar_one()
        return properties, int(rows), copies

    async def count_by_automated(
        self, filters: UnderwritingAnalyticsFilters
    ) -> list[tuple[bool | None, int]]:
        query = (
            select(Underwriting.is_automated, func.count())
            .where(*underwriting_filter_conditions(filters))
            .group_by(Underwriting.is_automated)
        )
        result = await self.db.execute(query)
        return [(flag, count) for flag, count in result.all()]

    async def job_health(
        self, *, created_from: date | None = None, created_to: date | None = None
    ) -> list[tuple[str, str, int, datetime | None]]:
        query = (
            select(Job.job_type, Job.status, func.count(), func.max(Job.finished_at))
            .where(*date_range_conditions(Job.created_at, created_from, created_to))
            .group_by(Job.job_type, Job.status)
        )
        result = await self.db.execute(query)
        return [tuple(row) for row in result.all()]

    async def completeness(
        self, filters: UnderwritingAnalyticsFilters
    ) -> dict[str, int]:
        query = select(
            func.count().label("total"),
            func.count()
            .filter(Underwriting.market_id.is_(None))
            .label("missing_market"),
            func.count()
            .filter(Underwriting.analyst_id.is_(None))
            .label("missing_analyst"),
            func.count()
            .filter(Underwriting.purchase_price.is_(None))
            .label("missing_price"),
            func.count()
            .filter(Underwriting.deal_status.is_(None))
            .label("missing_status"),
        ).where(*underwriting_filter_conditions(filters))
        result = await self.db.execute(query)
        return dict(result.one()._mapping)


def _price_band_case(bands: PriceBandBounds):
    """``CASE`` mapping ``purchase_price`` to a band key; NULL price -> NULL.

    Bands are contiguous and ordered low to high, so each WHEN only needs the
    upper bound; the open-ended last band checks its lower bound so a NULL
    price matches nothing and falls through to NULL.
    """
    price = Underwriting.purchase_price
    whens = [
        (price < upper, literal(key))
        if upper is not None
        else (price >= lower, literal(key))
        for key, lower, upper in bands
    ]
    return case(*whens).label("band")
