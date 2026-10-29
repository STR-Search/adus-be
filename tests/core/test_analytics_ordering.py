from datetime import date

from app.core.analytics.ordering import (
    fill_series,
    order_fixed,
    order_open,
    order_ranked,
    period_start,
)
from app.core.analytics.schemas import BreakdownItem, Granularity, GroupRow, ratio

KNOWN = (("a", "A"), ("b", "B"), ("c", "C"))


def _keys(items):
    return [(item.key, item.count) for item in items]


# Rule 1 ----------------------------------------------------------------------


def test_fixed_zero_fills_known_in_defined_order():
    items = order_fixed({"c": 2, "a": 1}, known=KNOWN)

    assert _keys(items) == [("a", 1), ("b", 0), ("c", 2)]
    assert [item.label for item in items] == ["A", "B", "C"]


def test_fixed_unknown_keys_after_known_by_key_and_none_last():
    items = order_fixed({None: 3, "zeta": 1, "alpha": 2, "b": 5}, known=KNOWN)

    assert _keys(items) == [("a", 0), ("b", 5), ("c", 0), ("alpha", 2), ("zeta", 1), (None, 3)]
    assert items[-1].label == "Unknown"


def test_fixed_none_only_present_when_non_zero():
    assert _keys(order_fixed({None: 0}, known=KNOWN)) == [("a", 0), ("b", 0), ("c", 0)]


def test_fixed_narrowed_known_zero_fills_only_those():
    assert _keys(order_fixed({}, known=KNOWN[1:])) == [("b", 0), ("c", 0)]


# Rule 2 ----------------------------------------------------------------------


def test_open_breaks_ties_by_key_regardless_of_input_order():
    rows = [BreakdownItem(key=k, label=k, count=c) for k, c in [("z", 2), ("m", 5), ("a", 2)]]

    assert _keys(order_open(rows)) == [("m", 5), ("a", 2), ("z", 2)]
    assert _keys(order_open(reversed(rows))) == [("m", 5), ("a", 2), ("z", 2)]


def test_open_none_last_even_with_highest_count():
    rows = [
        BreakdownItem(key=None, label="Unknown", count=99),
        BreakdownItem(key="x", label="X", count=1),
    ]

    assert _keys(order_open(rows)) == [("x", 1), (None, 99)]


# Rule 3 ----------------------------------------------------------------------


class _Row(GroupRow):
    n: int | None


def test_ranked_by_value_then_label_then_key_unassigned_last():
    rows = [
        _Row(key=None, label="Unassigned", n=100),
        _Row(key="2", label="Boston", n=5),
        _Row(key="1", label="Boston", n=5),
        _Row(key="3", label="Austin", n=5),
        _Row(key="4", label="Zion", n=9),
    ]

    ordered = order_ranked(rows, by="n")

    assert [row.key for row in ordered] == ["4", "3", "1", "2", None]


def test_ranked_treats_none_value_as_zero():
    # Rates are None over a zero denominator.
    rows = [_Row(key="1", label="A", n=None), _Row(key="2", label="B", n=1)]

    assert [row.key for row in order_ranked(rows, by="n")] == ["2", "1"]


# Rule 4 ----------------------------------------------------------------------


def test_series_fills_empty_middle_week():
    points = fill_series(
        {date(2026, 9, 28): 3, date(2026, 10, 12): 1},
        start=None,
        end=None,
        granularity=Granularity.WEEK,
    )

    assert [(p.period_start, p.count) for p in points] == [
        (date(2026, 9, 28), 3),
        (date(2026, 10, 5), 0),
        (date(2026, 10, 12), 1),
    ]


def test_series_spans_requested_range_snapped_to_monday():
    points = fill_series(
        {}, start=date(2026, 10, 1), end=date(2026, 10, 14), granularity=Granularity.WEEK
    )

    assert [p.period_start for p in points] == [
        date(2026, 9, 28),
        date(2026, 10, 5),
        date(2026, 10, 12),
    ]


def test_series_empty_without_range_or_data():
    assert fill_series({}, start=None, end=None, granularity=Granularity.DAY) == []


def test_period_start_week_is_monday():
    assert period_start(date(2026, 10, 25), Granularity.WEEK) == date(2026, 10, 19)
    assert period_start(date(2026, 10, 25), Granularity.DAY) == date(2026, 10, 25)


def test_ratio_is_none_over_zero():
    assert ratio(1, 4) == 0.25
    assert ratio(0, 0) is None
