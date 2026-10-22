from pydantic import BaseModel

from app.core.analytics.schemas import Breakdown, BreakdownItem, GroupRow, MedianValue


class CoverageRow(GroupRow):
    listings: int
    underwritten: int
    # underwritten / listings.
    coverage: float | None
    # Days from the listing's first-seen time to its earliest underwriting.
    median_days_to_underwrite: float | None


class Coverage(BaseModel):
    # key None, label "All presets".
    overall: CoverageRow
    presets: list[CoverageRow]


class OffMarketStatusRow(BaseModel):
    # deal_status; None = no status.
    key: str | None
    label: str
    off_market: int
    # Raw Zillow home_status (PENDING, SOLD, ...).
    by_home_status: list[BreakdownItem]


class OffMarket(BaseModel):
    # Metric 10.
    by_status: list[OffMarketStatusRow]
    # Metric 11: present_to_clients and off the market. A deal under contract
    # that went off the market is a win, not a miss, so it is not counted.
    missed_deals: int
    # Denominator for missed_deals: every present_to_clients deal.
    presented_total: int
    # missed_deals / presented_total.
    missed_rate: float | None
    # Metric 12: still in analysis (ANALYSIS_STATUSES) and off the market.
    wasted_analysis: int


class PriceDrops(BaseModel):
    # Live deals (status set, not terminal) whose listing's price was cut.
    deals: Breakdown
    # Positive fraction of the pre-drop price (0.05 = cut by 5%).
    median_drop_pct: MedianValue
