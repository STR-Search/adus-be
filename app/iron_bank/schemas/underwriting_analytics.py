from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.analytics.schemas import Breakdown, BreakdownItem, GroupRow, MedianValue
from app.iron_bank.enums import DealStatus, UnderwritingSource

# Every row created in the current system. ``legacy_sheet`` (the 2,021 rows
# backfilled from the old Google Sheet) is opt-in: blank underwritings move
# through the same deal statuses as adus rows, only their listing data is typed.
DEFAULT_ANALYTICS_SOURCES: tuple[UnderwritingSource, ...] = (
    UnderwritingSource.ADUS,
    UnderwritingSource.BLANK,
)


class UnderwritingAnalyticsFilters(BaseModel):
    """The population an underwriting metric counts.

    Shared by every underwriting and cross-domain analytics query so they all
    narrow the same way. ``deal_status=None`` means every status; a market or
    analyst of ``None`` means "don't filter", not "unassigned".
    """

    model_config = ConfigDict(frozen=True)

    market_id: int | None = None
    analyst_id: int | None = None
    source: tuple[UnderwritingSource, ...] = DEFAULT_ANALYTICS_SOURCES
    # Inclusive whole UTC days on ``deal_added``.
    added_from: date | None = None
    added_to: date | None = None
    deal_status: tuple[DealStatus, ...] | None = None


class TemplateProgressPoint(BaseModel):
    period_start: date
    created: int
    past_template: int
    # past_template / created; None when created == 0.
    share: float | None


class MarketRow(GroupRow):
    underwritten: int
    by_status: list[BreakdownItem]
    # deal_status in PRESENTED_STATUSES (a deal under contract was presented first).
    presented: int
    # deal_status in WON_STATUSES.
    won: int
    # presented / underwritten.
    presented_rate: float | None
    # won / presented.
    win_rate: float | None


class MarketBreakdown(BaseModel):
    # key None, label "All markets".
    overall: MarketRow
    markets: list[MarketRow]


class PriceBandRow(GroupRow):
    total: int
    by_status: list[BreakdownItem]


class QualityGroup(BaseModel):
    key: Literal["presented", "deleted"]
    label: str
    # The DealStatus values this group covers.
    statuses: list[str]
    deals: int
    median_cash_on_cash: MedianValue
    median_deal_score: MedianValue
    median_total_oop: MedianValue


class QualityComparison(BaseModel):
    groups: list[QualityGroup]


class DeleteReasonRow(GroupRow):
    total: int
    # delete_zillow ("bad listing") and delete_deal ("bad numbers").
    by_status: list[BreakdownItem]


class DeleteReasons(BaseModel):
    overall: DeleteReasonRow
    markets: list[DeleteReasonRow]


class TagMix(BaseModel):
    """Tag counts per field, keyed by field name.

    ``total`` of each breakdown is the number of deals. For multi-select fields
    an item's ``count`` is the number of deals carrying that tag, so the items
    can sum to more than ``total``; the ``None`` item is deals with no tag.
    """

    fields: dict[str, Breakdown]


class Duplicates(BaseModel):
    # zpids underwritten under more than one series.
    properties_underwritten_repeatedly: int
    # Every underwriting row on those zpids.
    underwritings_on_those_properties: int
    # Rows made with the Duplicate button (copied_from_id set).
    duplicate_button_copies: int


class JobTypeHealth(BaseModel):
    key: str
    label: str
    total: int
    # queued / running / succeeded / failed, in that order, zeros filled.
    by_status: list[BreakdownItem]
    last_finished_at: datetime | None


class UnderwritingCompleteness(BaseModel):
    total: int
    missing_market: int
    missing_analyst: int
    missing_price: int
    missing_status: int
