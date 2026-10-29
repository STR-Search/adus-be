from datetime import date

from sqlalchemy import Column, DateTime, Integer, MetaData, Table, select
from sqlalchemy.dialects import postgresql

from app.core.query_filters import date_range_conditions, numeric_range_conditions

_table = Table(
    "t",
    MetaData(),
    Column("at", DateTime(timezone=True)),
    Column("n", Integer),
)


def _where(conditions) -> str:
    query = select(_table.c.n).where(*conditions)
    return str(
        query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def test_min_equals_max_covers_that_whole_utc_day():
    sql = _where(date_range_conditions(_table.c.at, date(2026, 10, 1), date(2026, 10, 1)))

    assert "t.at >= '2026-10-01 00:00:00+00:00'" in sql
    assert "t.at < '2026-10-02 00:00:00+00:00'" in sql


def test_upper_bound_is_exclusive_of_the_next_day():
    (only,) = date_range_conditions(_table.c.at, None, date(2026, 10, 3))

    assert "t.at < '2026-10-04 00:00:00+00:00'" in _where([only])


def test_open_date_range_has_no_conditions():
    assert date_range_conditions(_table.c.at, None, None) == []


def test_numeric_range_is_inclusive_either_end_open():
    lower, upper = numeric_range_conditions(_table.c.n, 2, 4)
    (only,) = numeric_range_conditions(_table.c.n, None, 4)

    assert "t.n >= 2" in _where([lower])
    assert "t.n <= 4" in _where([upper])
    assert "t.n <= 4" in _where([only])
    assert numeric_range_conditions(_table.c.n, None, None) == []
