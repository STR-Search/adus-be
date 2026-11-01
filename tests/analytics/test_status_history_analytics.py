from datetime import date

import pytest

from app.analytics.repositories.status_history_analytics_repository import (
    StatusHistoryAnalyticsRepository,
)
from app.analytics.services.pipeline_analytics_service import LIVE_STATUSES
from app.analytics.services.status_history_analytics_service import (
    ANALYST_STATUSES,
    BACKLOG_AGE_BUCKETS,
    StatusHistoryAnalyticsService,
)
from app.core.analytics.schemas import Granularity
from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.underwriting_analytics import UnderwritingAnalyticsFilters
from tests.analytics.conftest import CapturingDb, row, sql
from tests.analytics.test_pipeline_analytics import FakeRepository

BUCKETS = [(key, lower, upper) for key, _, lower, upper in BACKLOG_AGE_BUCKETS]


# Repository ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backlog_age_measures_from_latest_log_row_when_in_step():
    db = CapturingDb([])

    await StatusHistoryAnalyticsRepository(db).backlog_age(
        UnderwritingAnalyticsFilters(market_id=3),
        statuses=(DealStatus.ANALYST_COMPLETED,),
        buckets=BUCKETS,
        group_by_status=True,
    )

    query = sql(db.queries[0])
    # Latest row per deal: chain order is id order.
    assert "DISTINCT ON (process_log.transitions.subject_id)" in query
    assert (
        "ORDER BY process_log.transitions.subject_id, process_log.transitions.id DESC"
        in query
    )
    assert "LEFT OUTER JOIN" in query
    # Falls back to updated_at when the log is missing or out of step.
    assert (
        "CASE WHEN (anon_1.to_status = iron_bank.underwritings.deal_status) "
        "THEN anon_1.occurred_at ELSE coalesce(iron_bank.underwritings.updated_at, "
        "iron_bank.underwritings.created_at) END"
    ) in query
    assert "anon_1.source != 'backfill'" in query
    assert "iron_bank.underwritings.market_id = 3" in query
    assert "deal_status IN ('analyst_completed')" in query
    assert "GROUP BY iron_bank.underwritings.deal_status" in query


@pytest.mark.asyncio
async def test_backlog_age_overall_row_is_ungrouped():
    db = CapturingDb([row(deals=2)])

    (overall,) = await StatusHistoryAnalyticsRepository(db).backlog_age(
        UnderwritingAnalyticsFilters(),
        statuses=LIVE_STATUSES,
        buckets=BUCKETS,
        group_by_status=False,
    )

    assert "GROUP BY" not in sql(db.queries[0])
    assert overall == {"deals": 2, "deal_status": None}


@pytest.mark.asyncio
async def test_time_to_present_takes_earlier_of_log_and_deal_approved():
    db = CapturingDb([row(median_days=1, p75_days=2, measured=3, observed=1)])

    await StatusHistoryAnalyticsRepository(db).time_to_present(
        UnderwritingAnalyticsFilters(market_id=3),
        presented_from=date(2026, 10, 1),
        presented_to=date(2026, 10, 31),
    )

    query = sql(db.queries[0])
    presented_at = "least(anon_1.presented_at, iron_bank.underwritings.deal_approved)"
    assert f"{presented_at} >= iron_bank.underwritings.deal_added" in query
    assert f"{presented_at} >= '2026-10-01 00:00:00+00:00'" in query
    assert f"{presented_at} < '2026-11-01 00:00:00+00:00'" in query
    assert "to_status = 'present_to_clients'" in query
    assert "source != 'backfill'" in query
    assert "percentile_cont(0.75)" in query
    assert "iron_bank.underwritings.market_id = 3" in query


@pytest.mark.asyncio
async def test_moved_to_counts_logged_changes_in_the_occurred_range():
    db = CapturingDb([])

    await StatusHistoryAnalyticsRepository(db).moved_to_by_actor(
        UnderwritingAnalyticsFilters(market_id=3),
        ANALYST_STATUSES,
        occurred_from=date(2026, 10, 1),
    )

    query = sql(db.queries[0])
    assert "count(DISTINCT process_log.transitions.subject_id)" in query
    assert "to_status IN ('analyst_started', 'analyst_completed')" in query
    assert "source != 'backfill'" in query
    assert "occurred_at >= '2026-10-01 00:00:00+00:00'" in query
    assert "iron_bank.underwritings.market_id = 3" in query
    assert "GROUP BY process_log.transitions.actor_user_id" in query


@pytest.mark.asyncio
async def test_moved_to_by_period_buckets_by_week_of_the_change():
    db = CapturingDb([])

    await StatusHistoryAnalyticsRepository(db).moved_to_by_actor_and_period(
        UnderwritingAnalyticsFilters(),
        DealStatus.PRESENT_TO_CLIENTS,
        Granularity.WEEK,
    )

    assert (
        "date_trunc('week', timezone('UTC', process_log.transitions.occurred_at))"
        in sql(db.queries[0])
    )


@pytest.mark.asyncio
async def test_user_names_skips_the_query_without_ids():
    db = CapturingDb()
    assert await StatusHistoryAnalyticsRepository(db).user_names([]) == {}
    assert db.queries == []


@pytest.mark.asyncio
async def test_user_names_falls_back_to_email():
    db = CapturingDb(
        [(1, "Ana", "Lee", "a@x"), (2, None, None, "b@x"), (3, None, None, None)]
    )
    names = await StatusHistoryAnalyticsRepository(db).user_names([1, 2, 3])
    assert names == {1: "Ana Lee", 2: "b@x"}


# Service ---------------------------------------------------------------------


def backlog_row(deal_status, deals, **counts):
    return {
        "deal_status": deal_status,
        "deals": deals,
        "under_3d": 0,
        "3_7d": 0,
        "7_14d": 0,
        "over_14d": 0,
        "observed": 0,
        "median_days": None,
        "measured": 0,
        **counts,
    }


@pytest.mark.asyncio
async def test_backlog_age_zero_fills_statuses_and_buckets():
    def backlog(kwargs):
        if kwargs["group_by_status"]:
            return [
                backlog_row(
                    "analyst_completed",
                    5,
                    under_3d=1,
                    over_14d=3,
                    observed=2,
                    median_days=20.5,
                    measured=4,
                )
            ]
        return [backlog_row(None, 5, under_3d=1, over_14d=3, measured=4)]

    repo = FakeRepository(backlog_age=backlog)
    result = await StatusHistoryAnalyticsService(repo).get_backlog_age(
        UnderwritingAnalyticsFilters()
    )

    assert [r.key for r in result.by_status] == [s.value for s in LIVE_STATUSES]
    completed = next(r for r in result.by_status if r.key == "analyst_completed")
    assert [(i.key, i.count) for i in completed.by_age] == [
        ("under_3d", 1),
        ("3_7d", 0),
        ("7_14d", 0),
        ("over_14d", 3),
        (None, 1),  # no date to measure from
    ]
    assert completed.median_days.value == 20.5
    assert completed.observed == 2
    empty = next(r for r in result.by_status if r.key == "maybe")
    assert empty.deals == 0 and [i.key for i in empty.by_age] == [
        k for k, *_ in BACKLOG_AGE_BUCKETS
    ]
    assert result.overall.label == "All statuses"


@pytest.mark.asyncio
async def test_backlog_age_status_filter_intersects_live_statuses():
    repo = FakeRepository(
        backlog_age=lambda kwargs: (
            [] if kwargs["group_by_status"] else [backlog_row(None, 0)]
        )
    )
    result = await StatusHistoryAnalyticsService(repo).get_backlog_age(
        UnderwritingAnalyticsFilters(
            deal_status=(DealStatus.ANALYST_COMPLETED, DealStatus.DELETE_DEAL)
        )
    )
    assert [r.key for r in result.by_status] == ["analyst_completed"]


@pytest.mark.asyncio
async def test_time_to_present_splits_observed_and_estimated():
    repo = FakeRepository(
        time_to_present={
            "median_days": 6.0,
            "p75_days": 11.5,
            "measured": 10,
            "observed": 4,
        }
    )
    result = await StatusHistoryAnalyticsService(repo).get_time_to_present(
        UnderwritingAnalyticsFilters()
    )
    assert result.median_days.value == 6.0
    assert result.median_days.sample_size == 10
    assert result.p75_days == 11.5
    assert (result.observed, result.estimated) == (4, 6)


@pytest.mark.asyncio
async def test_team_output_ranks_people_and_fills_weeks():
    repo = FakeRepository(
        moved_to_by_actor=[
            (7, "analyst_started", 4),
            (7, "analyst_completed", 2),
            (8, "analyst_completed", 5),
            (None, "analyst_started", 9),
        ],
        moved_to_by_actor_and_period=[
            (9, date(2026, 10, 19), 1),
            (9, date(2026, 11, 2), 2),
            (10, date(2026, 10, 26), 5),
        ],
        user_names={7: "Ana", 8: "Ben", 9: "Cy"},
    )

    result = await StatusHistoryAnalyticsService(repo).get_team_output(
        UnderwritingAnalyticsFilters(), occurred_from=date(2026, 10, 19)
    )

    assert [(r.key, r.label, r.started, r.completed) for r in result.analysts] == [
        ("8", "Ben", 0, 5),
        ("7", "Ana", 4, 2),
        (None, "Unknown", 9, 0),
    ]
    assert [(s.key, s.label) for s in result.presented_by_approver] == [
        ("10", "User 10"),
        ("9", "Cy"),
    ]
    weeks = [date(2026, 10, 19), date(2026, 10, 26), date(2026, 11, 2)]
    # Every approver's series covers the same weeks, so the lines align.
    for series in result.presented_by_approver:
        assert [p.period_start for p in series.points] == weeks
    cy = result.presented_by_approver[1]
    assert [p.count for p in cy.points] == [1, 0, 2]
    assert ("user_names", ([7, 8, 9, 10],), {}) in repo.calls
