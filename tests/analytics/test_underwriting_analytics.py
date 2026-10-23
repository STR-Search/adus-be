from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.core.analytics.schemas import Granularity
from app.iron_bank.enums import DealStatus, UnderwritingSource
from app.iron_bank.repositories.underwriting_analytics_repository import (
    UnderwritingAnalyticsRepository,
)
from app.iron_bank.schemas.underwriting_analytics import UnderwritingAnalyticsFilters
from app.iron_bank.services.analytics.underwriting_analytics_service import (
    ANALYSIS_STATUSES,
    DELETED_STATUSES,
    PRESENTED_STATUSES,
    PRICE_BANDS,
    WON_STATUSES,
    MarketSort,
    UnderwritingAnalyticsService,
)
from app.iron_bank.services.deal_status_service import STATUS_OPTIONS
from tests.analytics.conftest import CapturingDb, row, sql

ALL_STATUSES = [status.value for status, _, _ in STATUS_OPTIONS]


class FakeRepository:
    """Returns canned rows per method and records the filters it was called with."""

    def __init__(self, **responses):
        self.responses = responses
        self.calls = []

    def __getattr__(self, name):
        async def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self.responses[name]

        return method


class FakeReferenceData:
    def __init__(self, labels):
        self.labels = labels
        self.calls = []

    async def get_label_map(self, **kwargs):
        self.calls.append(kwargs)
        return self.labels


def _items(items):
    return [(item.key, item.count) for item in items]


# Definitions -----------------------------------------------------------------


def test_status_constants_hold_only_deal_statuses():
    for constant in (
        PRESENTED_STATUSES,
        WON_STATUSES,
        DELETED_STATUSES,
        ANALYSIS_STATUSES,
    ):
        assert constant
        assert all(isinstance(status, DealStatus) for status in constant)


def test_price_bands_are_contiguous_and_non_overlapping():
    assert PRICE_BANDS[0][2] is None
    assert PRICE_BANDS[-1][3] is None
    for (_, _, _, upper), (_, _, lower, _) in zip(PRICE_BANDS, PRICE_BANDS[1:]):
        assert upper == lower


# Repository ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repository_applies_every_filter():
    db = CapturingDb([("maybe", 3)])

    rows = await UnderwritingAnalyticsRepository(db).count_by_deal_status(
        UnderwritingAnalyticsFilters(
            market_id=7,
            analyst_id=3,
            added_from=date(2026, 10, 1),
            added_to=date(2026, 10, 1),
            deal_status=(DealStatus.MAYBE, DealStatus.DELETE_DEAL),
        )
    )

    assert rows == [("maybe", 3)]
    query = sql(db.queries[0])
    assert "GROUP BY iron_bank.underwritings.deal_status" in query
    assert "iron_bank.underwritings.market_id = 7" in query
    assert "iron_bank.underwritings.analyst_id = 3" in query
    assert "deal_status IN ('maybe', 'delete_deal')" in query
    # min == max still covers that whole UTC day.
    assert "deal_added >= '2026-10-01 00:00:00+00:00'" in query
    assert "deal_added < '2026-10-02 00:00:00+00:00'" in query


@pytest.mark.asyncio
async def test_repository_defaults_to_current_system_sources_only():
    db = CapturingDb()

    await UnderwritingAnalyticsRepository(db).count_by_deal_status(
        UnderwritingAnalyticsFilters()
    )

    query = sql(db.queries[0])
    assert "source IN ('adus', 'blank')" in query
    assert "market_id =" not in query
    assert "analyst_id =" not in query
    assert "deal_added >=" not in query


@pytest.mark.asyncio
async def test_repository_source_filter_can_include_legacy_rows():
    db = CapturingDb()

    await UnderwritingAnalyticsRepository(db).count_by_deal_status(
        UnderwritingAnalyticsFilters(source=tuple(UnderwritingSource))
    )

    assert "source IN ('adus', 'legacy_sheet', 'blank')" in sql(db.queries[0])


@pytest.mark.asyncio
async def test_repository_template_progress_buckets_utc_weeks():
    db = CapturingDb()

    await UnderwritingAnalyticsRepository(db).template_progress(
        UnderwritingAnalyticsFilters(), Granularity.WEEK
    )

    query = sql(db.queries[0])
    assert (
        "date_trunc('week', timezone('UTC', iron_bank.underwritings.deal_added))"
        in query
    )
    assert "deal_status != 'template_generated'" in query


@pytest.mark.asyncio
async def test_repository_price_band_case_has_open_ends():
    db = CapturingDb()

    await UnderwritingAnalyticsRepository(db).count_by_price_band_and_status(
        UnderwritingAnalyticsFilters(),
        [(key, lower, upper) for key, _, lower, upper in PRICE_BANDS],
    )

    query = sql(db.queries[0])
    assert (
        "WHEN (iron_bank.underwritings.purchase_price < 300000) THEN 'under_300k'"
        in query
    )
    assert (
        "WHEN (iron_bank.underwritings.purchase_price >= 1000000) THEN 'over_1m'"
        in query
    )
    assert "ELSE" not in query


@pytest.mark.asyncio
async def test_repository_duplicates_counts_zpids_with_several_series():
    db = CapturingDb([(2, Decimal(5))], [(9,)])

    result = await UnderwritingAnalyticsRepository(db).duplicates(
        UnderwritingAnalyticsFilters()
    )

    assert result == (2, 5, 9)
    repeated, copies = (sql(q) for q in db.queries)
    assert "HAVING count(DISTINCT iron_bank.underwritings.series_id) > 1" in repeated
    assert "copied_from_id IS NOT NULL" in copies


@pytest.mark.asyncio
async def test_repository_multi_select_tags_unnest_and_count_untagged():
    db = CapturingDb([(10, 3)], [("lake", 4), ("ski", 2)])

    deals, rows = await UnderwritingAnalyticsRepository(db).count_tags(
        UnderwritingAnalyticsFilters(), "market_type", multi_select=True
    )

    assert deals == 10
    assert rows == [("lake", 4), ("ski", 2), (None, 3)]
    assert "unnest(iron_bank.underwritings.market_type)" in sql(db.queries[1])


# Service: deal-status-breakdown -----------------------------------------------


@pytest.mark.asyncio
async def test_breakdown_zero_fills_every_status_in_workflow_order():
    repo = FakeRepository(
        count_by_deal_status=[
            ("present_to_clients", 2),
            (None, 1),
            ("legacy_value", 4),
            ("template_generated", 10),
        ]
    )

    result = await UnderwritingAnalyticsService(repo).get_deal_status_breakdown(
        UnderwritingAnalyticsFilters(market_id=7)
    )

    assert result.total == 17
    assert [item.key for item in result.items] == [*ALL_STATUSES, "legacy_value", None]
    by_key = {item.key: item for item in result.items}
    assert by_key["template_generated"].label == "Template Generated"
    assert by_key["analyst_started"].count == 0
    assert by_key["legacy_value"].label == "legacy_value"
    assert by_key[None].label == "No Status"


@pytest.mark.asyncio
async def test_breakdown_with_status_filter_zero_fills_only_those():
    repo = FakeRepository(count_by_deal_status=[("client_under_contract", 3)])
    filters = UnderwritingAnalyticsFilters(deal_status=PRESENTED_STATUSES)

    result = await UnderwritingAnalyticsService(repo).get_deal_status_breakdown(filters)

    assert _items(result.items) == [
        ("present_to_clients", 0),
        ("client_under_contract", 3),
    ]


@pytest.mark.asyncio
async def test_breakdown_empty_still_lists_every_status():
    repo = FakeRepository(count_by_deal_status=[])

    result = await UnderwritingAnalyticsService(repo).get_deal_status_breakdown(
        UnderwritingAnalyticsFilters()
    )

    assert result.total == 0
    assert [item.key for item in result.items] == ALL_STATUSES


# Service: other metrics ------------------------------------------------------


@pytest.mark.asyncio
async def test_template_progress_fills_gaps_with_null_seen():
    repo = FakeRepository(
        template_progress=[(date(2026, 9, 28), 4, 1), (date(2026, 10, 12), 2, 2)]
    )

    points = await UnderwritingAnalyticsService(repo).get_template_progress(
        UnderwritingAnalyticsFilters(), Granularity.WEEK
    )

    assert [(p.period_start, p.created, p.past_template, p.seen) for p in points] == [
        (date(2026, 9, 28), 4, 1, 0.25),
        (date(2026, 10, 5), 0, 0, None),
        (date(2026, 10, 12), 2, 2, 1.0),
    ]


@pytest.mark.asyncio
async def test_market_breakdown_rates_labels_and_order():
    repo = FakeRepository(
        count_by_market_and_status=[
            (1, "present_to_clients", 3),
            (1, "client_under_contract", 1),
            (1, "template_generated", 4),
            (2, "template_generated", 8),
            (None, "delete_deal", 20),
            (99, "maybe", 8),
        ]
    )

    result = await UnderwritingAnalyticsService(repo).get_market_breakdown(
        UnderwritingAnalyticsFilters(),
        market_labels={1: "Asheville", 2: "Boston"},
    )

    assert result.overall.label == "All markets"
    assert result.overall.underwritten == 44
    assert [(m.key, m.label) for m in result.markets] == [
        # 8 each: tie broken by label; unassigned last despite the most rows.
        ("1", "Asheville"),
        ("2", "Boston"),
        ("99", "Market 99"),
        (None, "Unassigned"),
    ]
    asheville = result.markets[0]
    assert (asheville.presented, asheville.won) == (4, 1)
    assert asheville.presented_rate == 0.5
    assert asheville.win_rate == 0.25
    assert "by_status" not in asheville.model_dump()
    assert result.markets[1].win_rate is None


@pytest.mark.asyncio
async def test_market_breakdown_sort_by_win_rate():
    repo = FakeRepository(
        count_by_market_and_status=[
            (1, "template_generated", 50),
            (1, "present_to_clients", 1),
            (2, "client_under_contract", 1),
        ]
    )

    result = await UnderwritingAnalyticsService(repo).get_market_breakdown(
        UnderwritingAnalyticsFilters(),
        market_labels={1: "A", 2: "B"},
        sort=MarketSort.WIN_RATE,
    )

    assert [m.key for m in result.markets] == ["2", "1"]


@pytest.mark.asyncio
async def test_price_bands_zero_fill_and_unpriced_last():
    repo = FakeRepository(
        count_by_price_band_and_status=[("over_1m", "maybe", 2), (None, "maybe", 1)]
    )

    rows = await UnderwritingAnalyticsService(repo).get_price_bands(
        UnderwritingAnalyticsFilters()
    )

    assert [(r.key, r.total) for r in rows] == [
        ("under_300k", 0),
        ("300k_500k", 0),
        ("500k_750k", 0),
        ("750k_1m", 0),
        ("over_1m", 2),
        (None, 1),
    ]
    assert [item.key for item in rows[0].by_status] == ALL_STATUSES


@pytest.mark.asyncio
async def test_price_bands_omit_unpriced_row_when_empty():
    repo = FakeRepository(count_by_price_band_and_status=[])

    rows = await UnderwritingAnalyticsService(repo).get_price_bands(
        UnderwritingAnalyticsFilters()
    )

    assert None not in [r.key for r in rows]


@pytest.mark.asyncio
async def test_quality_comparison_reports_groups_and_sample_sizes():
    medians = row(
        deals=5,
        cash_on_cash_median=Decimal("0.09"),
        cash_on_cash_count=5,
        total_oop_median=300000.0,
        total_oop_count=4,
    )._mapping
    repo = FakeRepository(quality_medians=medians)

    result = await UnderwritingAnalyticsService(repo).get_quality_comparison(
        UnderwritingAnalyticsFilters()
    )

    presented, deleted = result.groups
    assert presented.key == "presented"
    assert presented.statuses == ["present_to_clients", "client_under_contract"]
    assert deleted.statuses == ["delete_zillow", "delete_deal"]
    assert presented.median_cash_on_cash.value == 0.09
    assert presented.median_total_oop.sample_size == 4
    assert "median_deal_score" not in presented.model_dump()
    assert [call[1][1] for call in repo.calls] == [PRESENTED_STATUSES, DELETED_STATUSES]


@pytest.mark.asyncio
async def test_tag_mix_defaults_to_presented_and_resolves_labels():
    repo = FakeRepository(count_tags=(4, [("lake", 1), ("retired", 3), (None, 2)]))
    reference = FakeReferenceData({("market_type", "lake"): "Lake"})

    result = await UnderwritingAnalyticsService(repo, reference).get_tag_mix(
        UnderwritingAnalyticsFilters()
    )

    filters = repo.calls[0][1][0]
    assert filters.deal_status == PRESENTED_STATUSES
    assert [call[2]["multi_select"] for call in repo.calls] == [True, True, False]
    market_type = result.fields["market_type"]
    assert market_type.total == 4
    assert [(i.key, i.label, i.count) for i in market_type.items] == [
        ("retired", "retired", 3),
        ("lake", "Lake", 1),
        (None, "Not Tagged", 2),
    ]


@pytest.mark.asyncio
async def test_automation_split_orders_automated_manual_unknown():
    repo = FakeRepository(count_by_automated=[(None, 1), (False, 2), (True, 5)])

    result = await UnderwritingAnalyticsService(repo).get_automation_split(
        UnderwritingAnalyticsFilters()
    )

    assert _items(result.items) == [("automated", 5), ("manual", 2), (None, 1)]


@pytest.mark.asyncio
async def test_job_health_zero_fills_statuses_and_keeps_latest_finish():
    early = datetime(2026, 10, 1, tzinfo=timezone.utc)
    late = datetime(2026, 10, 20, tzinfo=timezone.utc)
    repo = FakeRepository(
        job_health=[
            ("batch_prepare_by_preset", "succeeded", 10, late),
            ("batch_prepare_by_preset", "failed", 1, early),
            ("other_job", "queued", 2, None),
        ]
    )

    rows = await UnderwritingAnalyticsService(repo).get_job_health()

    assert [r.key for r in rows] == ["batch_prepare_by_preset", "other_job"]
    batch = rows[0]
    assert batch.label == "Batch Prepare By Preset"
    assert batch.total == 11
    assert _items(batch.by_status) == [
        ("queued", 0),
        ("running", 0),
        ("succeeded", 10),
        ("failed", 1),
    ]
    assert batch.last_finished_at == late
    assert rows[1].last_finished_at is None
