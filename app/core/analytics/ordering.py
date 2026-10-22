"""Display order for every list an analytics endpoint returns.

The order is part of the API contract: the frontend renders lists as received
and never re-sorts them. Services apply these after the repository returns
rows and never rely on SQL ``ORDER BY``, because zero-filling and merging
change the list after the query. The rule depends on what kind of category the
list holds (see docs/superpowers/specs/2026-10-22-analytics-api-design.md):

- ``order_fixed`` — ordered categories (deal statuses, price bands).
- ``order_open`` — open sets (raw Zillow statuses, tags, job types).
- ``order_ranked`` — per-group tables (markets, presets).
- ``fill_series`` — time series.
"""

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from typing import TypeVar

from app.core.analytics.schemas import BreakdownItem, Granularity, GroupRow, SeriesPoint

RowT = TypeVar("RowT", bound=GroupRow)


def order_fixed(
    counts: Mapping[str | None, int],
    *,
    known: Sequence[tuple[str, str]],
    unknown_label: str = "Unknown",
) -> list[BreakdownItem]:
    """Rule 1: known categories in their defined order, every one present.

    ``known`` is ``(key, label)`` pairs in display order; pass only the subset
    a filter asked for to zero-fill just those. Keys the caller does not know
    (e.g. a status a migration added before the enum was updated) follow, by
    key, so they are visible rather than dropped. The ``None`` item is last and
    only present when its count is above zero.
    """
    known_keys = {key for key, _ in known}
    items = [
        BreakdownItem(key=key, label=label, count=counts.get(key, 0))
        for key, label in known
    ]
    items.extend(
        BreakdownItem(key=key, label=key, count=count)
        for key, count in sorted(
            (item for item in counts.items() if item[0] is not None),
            key=lambda item: item[0],
        )
        if key not in known_keys
    )
    if counts.get(None):
        items.append(BreakdownItem(key=None, label=unknown_label, count=counts[None]))
    return items


def order_open(items: Iterable[BreakdownItem]) -> list[BreakdownItem]:
    """Rule 2: count descending, key ascending as tiebreaker, ``None`` last.

    The tiebreaker makes the order deterministic for identical data; Postgres
    promises no ``GROUP BY`` order, so equal counts would otherwise flicker.
    """
    return sorted(
        items, key=lambda item: (item.key is None, -item.count, item.key or "")
    )


def order_ranked(rows: Iterable[RowT], *, by: str) -> list[RowT]:
    """Rule 3: ``by`` descending, then label, then key; unassigned row last."""
    return sorted(
        rows,
        key=lambda row: (
            row.key is None,
            -(getattr(row, by) or 0),
            row.label,
            row.key or "",
        ),
    )


def period_start(day: date, granularity: Granularity) -> date:
    """The start of the day/week bucket ``day`` falls in (weeks start Monday)."""
    if granularity is Granularity.WEEK:
        return day - timedelta(days=day.weekday())
    return day


def _step(granularity: Granularity) -> timedelta:
    return timedelta(weeks=1) if granularity is Granularity.WEEK else timedelta(days=1)


def fill_periods(
    starts: Iterable[date],
    *,
    start: date | None,
    end: date | None,
    granularity: Granularity,
) -> list[date]:
    """Every period start from ``start`` to ``end``, inclusive, in order.

    Missing ends fall back to the first/last period with data. Empty when
    neither an end nor any data gives a range.
    """
    starts = sorted(starts)
    first = (
        period_start(start, granularity) if start else (starts[0] if starts else None)
    )
    last = period_start(end, granularity) if end else (starts[-1] if starts else first)
    if first is None or last is None or first > last:
        return []
    periods, step, current = [], _step(granularity), first
    while current <= last:
        periods.append(current)
        current += step
    return periods


def fill_series(
    counts: Mapping[date, int],
    *,
    start: date | None,
    end: date | None,
    granularity: Granularity,
) -> list[SeriesPoint]:
    """Rule 4: chronological, every period present, ``count: 0`` for gaps."""
    return [
        SeriesPoint(period_start=period, count=counts.get(period, 0))
        for period in fill_periods(
            counts, start=start, end=end, granularity=granularity
        )
    ]
