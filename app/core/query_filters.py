"""WHERE-clause builders shared across domains.

Pure functions over SQLAlchemy columns with no dependency on any domain, so
every domain's repositories (and the analytics composition layer) can build the
same range filters without importing each other.
"""

from datetime import date, datetime, time, timedelta, timezone


def date_range_conditions(column, minimum: date | None, maximum: date | None) -> list:
    """Half-open day-range conditions for a ``timestamptz`` column.

    The bounds arrive as calendar dates but the columns store instants, so a
    naive ``column <= maximum`` would compare against midnight and silently
    drop everything later that day — making min == max return nothing. The
    upper bound is therefore exclusive-of-the-next-day (``< max + 1 day``),
    which makes ``max`` fully inclusive and ``min == max`` mean "that one day".

    Bounds are anchored to UTC explicitly rather than left as bare dates for
    Postgres to cast, so results don't shift with the session's TimeZone.
    """
    conditions = []
    if minimum is not None:
        conditions.append(
            column >= datetime.combine(minimum, time.min, tzinfo=timezone.utc)
        )
    if maximum is not None:
        conditions.append(
            column
            < datetime.combine(
                maximum + timedelta(days=1), time.min, tzinfo=timezone.utc
            )
        )
    return conditions


def numeric_range_conditions(column, minimum, maximum) -> list:
    """Inclusive ``minimum <= column <= maximum`` conditions, either end open.

    The plain-number sibling of ``date_range_conditions``: no day-boundary
    adjustment is needed because the column holds the same kind of value the
    bounds do, so ``min == max`` compares equal directly. NULL never matches a
    bounded filter, which is the same answer the old ``==`` gave.
    """
    conditions = []
    if minimum is not None:
        conditions.append(column >= minimum)
    if maximum is not None:
        conditions.append(column <= maximum)
    return conditions
