"""Update ``markets.opex_by_bedrooms`` / ``markets.opex_by_size`` from a master CSV.

The durable replacement for the one-off ``seed_opex_by_bedrooms`` /
``update_opex_by_bedrooms_enigma`` scripts: it re-runs safely, prints what it
would change before changing it, and picks up new opex columns on its own.

Usage::

    # show the diff, write nothing (the default)
    uv run python scripts/seeding_scripts/update_opex_from_csv.py --table bedrooms
    # apply it
    uv run python scripts/seeding_scripts/update_opex_from_csv.py --table bedrooms --commit

Matching
--------
The CSV's first column is ``market_name``, resolved to ``market_id`` against
``markets.market_keys_master`` (live rows only). A row is then located by
``(market_id, bedrooms)`` -- or ``(market_id, sqft)`` for the size table -- and
its value columns are updated in place. This script **only updates**: a CSV row
with no live target row is reported and skipped, never inserted. Any ``id`` /
``market_id`` columns in the CSV are ignored as the source of truth, but are
cross-checked against the name lookup and abort the run if they disagree.

Cell formats
------------
``property_taxes``, ``land_value`` and ``appreciation`` are stored as
**fractions** (0.01, 0.16, 0.0425), while the CSV writes them as percentages
("1.00%", "16.00%", "4.25%"), so those cells are divided by 100. They are
required to carry a "%" -- a bare "1.00" in a percent column is a hundredfold
error, not a value to guess at, so it aborts the run. Every other column is a
plain amount; "$" and thousands separators are tolerated. A "%" appearing in a
column *not* declared as a percentage aborts too, which is what catches a
renamed or reordered header.

``null`` (any case) sets the column to NULL. An empty cell means "leave this
column alone" -- the two are deliberately different, so a CSV exported with
holes in it cannot silently blank out data.

Only fields whose value actually differs from what is stored are written, so a
second run is a no-op and a value that differs only in trailing zeros
(125 vs 125.00) is left at the scale the database already has.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(REPO_ROOT))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.markets.models import MarketKeysMaster, OpexByBedrooms, OpexBySize

DATA_DIR = REPO_ROOT / "scripts" / "data"

# Columns the CSV may carry that are not values to write. ``id`` and
# ``market_id`` are here rather than absent because the exports carry them;
# see the cross-check in ``resolve_market_ids``.
IGNORED_CSV_COLUMNS = frozenset({"market_name", "market_status", "id", "market_id"})
# Never written: server-assigned, or the keys we match on.
NON_VALUE_COLUMNS = frozenset({"id", "market_id", "deleted_at"})
# Cells that mean "store NULL", as opposed to an empty cell, which means
# "leave this column as it is".
NULL_SENTINELS = frozenset({"null", "none", "n/a", "na"})

LEAVE_UNCHANGED = object()


@dataclass(frozen=True)
class TableSpec:
    """One opex table and how its CSV maps onto it."""

    model: type
    key_column: str
    # Columns written as percentages in the CSV and stored as fractions. A
    # hand-kept set, guarded by the "%" check in ``parse_cell``: a new percent
    # column that is not listed here fails loudly rather than landing 100x off.
    percent_columns: frozenset[str]
    default_csv: Path

    @property
    def table_name(self) -> str:
        return self.model.__tablename__

    @property
    def value_columns(self) -> list[str]:
        """Every writable column, read off the model so new ones need no edit."""
        return [
            column.name
            for column in self.model.__table__.columns
            if column.name not in NON_VALUE_COLUMNS | {self.key_column}
        ]


SPECS = {
    "bedrooms": TableSpec(
        model=OpexByBedrooms,
        key_column="bedrooms",
        percent_columns=frozenset({"property_taxes", "land_value", "appreciation"}),
        default_csv=DATA_DIR / "opex-by-bedrooms-master.csv",
    ),
    "size": TableSpec(
        model=OpexBySize,
        key_column="sqft",
        percent_columns=frozenset(),
        default_csv=DATA_DIR / "opex-by-size-master.csv",
    ),
}


class CsvError(Exception):
    """A problem with the file itself — nothing is written when one is raised."""


def normalize(value: Decimal) -> Decimal:
    """Minimal representation, never scientific notation.

    ``Decimal("1.00") / 100`` is ``0.0100``; the stored figures are ``0.01``.
    Scale is visible on the wire (``PlainDecimal`` formats with ``f``), so the
    trailing zeros are stripped rather than persisted. ``normalize`` renders
    whole numbers as ``3.5E+2``, hence the re-quantize.
    """
    value = value.normalize()
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent > 0:
        value = value.quantize(Decimal(1))
    return value


def parse_cell(raw: str, *, column: str, is_percent: bool, where: str):
    """One cell to a Decimal, ``None`` (NULL) or ``LEAVE_UNCHANGED``."""
    text = raw.strip()
    if text == "":
        return LEAVE_UNCHANGED
    if text.lower() in NULL_SENTINELS:
        return None

    has_percent = text.endswith("%")
    if is_percent and not has_percent:
        raise CsvError(
            f"{where}: {column}={text!r} has no '%'. This column is stored as a "
            f"fraction; a bare number here would be 100x off. Write '1.00%' or "
            f"'null'."
        )
    if has_percent and not is_percent:
        raise CsvError(
            f"{where}: {column}={text!r} is a percentage, but {column} is stored "
            f"as a plain amount. Either the header is wrong or this column "
            f"belongs in the spec's percent_columns."
        )

    cleaned = text.rstrip("%").replace("$", "").replace(",", "").strip()
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise CsvError(f"{where}: {column}={text!r} is not a number") from None

    if is_percent:
        value = value / 100
    return normalize(value)


def load_csv(spec: TableSpec, path: Path) -> tuple[list[dict], list[str]]:
    """Parse and validate the whole file before anything touches the database."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        raw_rows = list(reader)

    if not raw_rows:
        raise CsvError(f"{path.name} has no data rows")

    known = set(spec.value_columns) | IGNORED_CSV_COLUMNS | {spec.key_column}
    unknown = [column for column in header if column not in known]
    if unknown:
        raise CsvError(
            f"{path.name}: unrecognised column(s) {unknown}. Known value columns "
            f"for {spec.table_name}: {sorted(spec.value_columns)}"
        )
    for required in ("market_name", spec.key_column):
        if required not in header:
            raise CsvError(f"{path.name}: required column '{required}' is missing")

    csv_value_columns = [column for column in spec.value_columns if column in header]
    if not csv_value_columns:
        raise CsvError(f"{path.name}: no value columns to update")

    rows = []
    for line, raw in enumerate(raw_rows, start=2):  # line 1 is the header
        market_name = (raw.get("market_name") or "").strip()
        key_text = (raw.get(spec.key_column) or "").strip()
        where = f"{path.name} line {line} ({market_name or '?'} / {key_text or '?'})"
        if not market_name:
            raise CsvError(f"{where}: market_name is empty")
        try:
            key_value = int(key_text)
        except ValueError:
            raise CsvError(
                f"{where}: {spec.key_column}={key_text!r} is not an integer"
            ) from None

        values = {
            column: parse_cell(
                raw.get(column) or "",
                column=column,
                is_percent=column in spec.percent_columns,
                where=where,
            )
            for column in csv_value_columns
        }
        rows.append(
            {
                "market_name": market_name,
                "key_value": key_value,
                "values": values,
                "csv_market_id": (raw.get("market_id") or "").strip(),
                "where": where,
            }
        )

    duplicates = [
        key
        for key, count in Counter(
            (row["market_name"], row["key_value"]) for row in rows
        ).items()
        if count > 1
    ]
    if duplicates:
        raise CsvError(
            f"{path.name}: duplicate (market_name, {spec.key_column}) rows "
            f"{sorted(duplicates)} — which one wins is undefined, so fix the file"
        )

    return rows, csv_value_columns


def resolve_market_ids(rows: list[dict], markets: list[MarketKeysMaster]) -> set[str]:
    """Stamp ``market_id`` on each row from its name; return the unresolved names.

    Where the CSV carries its own ``market_id``, it is treated as a checksum on
    the export rather than as input: a disagreement means the file's ids are
    stale, and silently preferring either one would write the wrong market.
    """
    by_name = {market.market_name: market.id for market in markets}

    mismatches = []
    unresolved = set()
    for row in rows:
        market_id = by_name.get(row["market_name"])
        row["market_id"] = market_id
        if market_id is None:
            unresolved.add(row["market_name"])
            continue
        if row["csv_market_id"] and int(row["csv_market_id"]) != market_id:
            mismatches.append(
                f"  {row['where']}: csv market_id={row['csv_market_id']}, "
                f"but '{row['market_name']}' is market_id={market_id}"
            )

    if mismatches:
        raise CsvError(
            "the CSV's market_id column disagrees with market_keys_master:\n"
            + "\n".join(mismatches)
        )
    return unresolved


def diff_row(record, values: dict) -> dict:
    """The fields that would actually change, old value included."""
    changes = {}
    for column, new in values.items():
        if new is LEAVE_UNCHANGED:
            continue
        old = getattr(record, column)
        # Numeric comparison: 125 and 125.00 are the same figure, and rewriting
        # one as the other would churn the stored scale for nothing.
        if old is None and new is None:
            continue
        if old is not None and new is not None and old == new:
            continue
        changes[column] = (old, new)
    return changes


def render(value) -> str:
    return "NULL" if value is None else format(value, "f")


async def run(spec: TableSpec, path: Path, *, commit: bool, verbose: bool) -> int:
    rows, csv_value_columns = load_csv(spec, path)
    print(f"{path.name}: {len(rows)} row(s), {len(csv_value_columns)} value column(s)")

    untouched = sorted(set(spec.value_columns) - set(csv_value_columns))
    if untouched:
        print(f"  not in this CSV, left as-is: {', '.join(untouched)}")
    blanks = Counter(
        column
        for row in rows
        for column, value in row["values"].items()
        if value is LEAVE_UNCHANGED
    )
    if blanks:
        print(f"  empty cells (left as-is): {dict(blanks)}")

    async with AsyncSessionLocal() as session:
        markets = (
            (
                await session.execute(
                    select(MarketKeysMaster).where(
                        MarketKeysMaster.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        unresolved = resolve_market_ids(rows, markets)

        existing = (
            (
                await session.execute(
                    select(spec.model).where(spec.model.deleted_at.is_(None))
                )
            )
            .scalars()
            .all()
        )
        by_key = {
            (record.market_id, getattr(record, spec.key_column)): record
            for record in existing
        }

        updated = 0
        unchanged = 0
        missing_rows = []
        per_column = Counter()

        for row in rows:
            if row["market_id"] is None:
                continue
            record = by_key.get((row["market_id"], row["key_value"]))
            if record is None:
                missing_rows.append(row)
                continue

            changes = diff_row(record, row["values"])
            if not changes:
                unchanged += 1
                continue

            for column, (old, new) in changes.items():
                setattr(record, column, new)
                per_column[column] += 1
            updated += 1
            if verbose:
                detail = ", ".join(
                    f"{column} {render(old)}->{render(new)}"
                    for column, (old, new) in sorted(changes.items())
                )
                print(
                    f"  {row['market_name']} / {spec.key_column}={row['key_value']}: "
                    f"{detail}"
                )

        if unresolved:
            print(f"\n  SKIPPED — not in market_keys_master ({len(unresolved)}):")
            for name in sorted(unresolved):
                print(f"    {name}")
        if missing_rows:
            by_market = defaultdict(list)
            for row in missing_rows:
                by_market[row["market_name"]].append(row["key_value"])
            print(
                f"\n  SKIPPED — no live {spec.table_name} row to update "
                f"({len(missing_rows)}):"
            )
            for name, keys in sorted(by_market.items()):
                print(f"    {name}: {spec.key_column}={sorted(keys)}")

        print(f"\n{spec.table_name}: {updated} row(s) to update, {unchanged} already current")
        if per_column:
            print("  changes per column:")
            for column, count in sorted(per_column.items(), key=lambda kv: -kv[1]):
                print(f"    {column:24} {count}")

        skipped = len(missing_rows) + sum(
            1 for row in rows if row["market_id"] is None
        )
        if not commit:
            await session.rollback()
            print("\nDRY RUN — nothing written. Re-run with --commit to apply.")
        elif updated:
            await session.commit()
            print(f"\nCommitted {updated} row(s).")
        else:
            await session.rollback()
            print("\nNothing to write.")

    return 1 if skipped else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", choices=sorted(SPECS), required=True)
    parser.add_argument("--csv", type=Path, help="defaults to the table's master CSV")
    parser.add_argument(
        "--commit", action="store_true", help="write the changes (default: dry run)"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="summary only, no per-row diff"
    )
    args = parser.parse_args()

    spec = SPECS[args.table]
    path = args.csv or spec.default_csv
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        return 2

    try:
        return asyncio.run(
            run(spec, path, commit=args.commit, verbose=not args.quiet)
        )
    except CsvError as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
