"""Seed every exploratory market's opex from its lookalike, driven by a CSV.

Batch runner for ``POST /markets/{market_id}/opex/seed-from-lookalike``. It
calls the same ``OpexSeedService`` the endpoint's controller calls, in-process
against ``DATABASE_URL`` -- no running server and no auth header -- which is how
the other opex scripts here are run in production (see
``docs/opex_by_bedrooms_update_script_run_production.md``). Every guard the API
enforces still applies, because it is the same code path.

Usage::

    # show the plan, write nothing (the default)
    uv run python scripts/seeding_scripts/seed_opex_from_lookalikes.py
    # apply it
    uv run python scripts/seeding_scripts/seed_opex_from_lookalikes.py --commit
    # a subset, by target market id
    uv run python scripts/seeding_scripts/seed_opex_from_lookalikes.py --only 47,50 --commit

CSV
---
``scripts/data/exploratory_market_lookalikes.csv``, three columns::

    id,market_slug,Lookalike market_id

``id`` is the target (exploratory) ``markets.market_keys_master.id``,
``market_slug`` is that same row's slug, and the third column is the active
market to copy from. The slug is not used for lookup -- the id is -- but it is
cross-checked against the id and a disagreement aborts the whole run before
anything is written, since that means the CSV is stale and no row in it can be
trusted. Header names are matched case-insensitively with spaces or underscores
either way, so "Lookalike market_id", "lookalike_market_id" and
"LOOKALIKE MARKET ID" all read the same.

Per-market isolation
--------------------
Each market is seeded in its own session and its own transaction, exactly as one
API call would be: a market that the service refuses is reported and the run
carries on with the rest. Nothing is half-written -- the service commits both
opex tables together or neither.

Re-running
----------
Safe. A market that already holds opex rows is refused by the service
(``OpexSeedTargetAlreadySeededError``, the endpoint's 409) and shows up here as
``already seeded``, so a run interrupted halfway can simply be repeated.

Exit codes: 0 everything seeded, 1 some rows skipped or refused, 2 the run
aborted before writing (bad CSV, id/slug mismatch).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(REPO_ROOT))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.markets.enums import MarketStatus
from app.markets.models import MarketKeysMaster
from app.markets.repositories.market_repository import MarketRepository
from app.markets.repositories.opex_repository import (
    OpexByBedroomsRepository,
    OpexBySizeRepository,
)
from app.markets.services.opex_service import OpexSeedError, OpexSeedService

DATA_DIR = REPO_ROOT / "scripts" / "data"
DEFAULT_CSV = DATA_DIR / "exploratory_market_lookalikes.csv"

TARGET_ID_HEADERS = frozenset({"id", "market_id"})
SLUG_HEADERS = frozenset({"market_slug", "slug"})
SOURCE_ID_HEADERS = frozenset({"lookalike_market_id", "lookalike_id", "source_market_id"})


class CsvError(Exception):
    """The CSV cannot be trusted; the run stops before touching the database."""


@dataclass(frozen=True)
class SeedRow:
    line: int
    target_id: int
    market_slug: str
    source_id: int

    def __str__(self) -> str:
        return f"{self.market_slug} ({self.target_id}) <- {self.source_id}"


@dataclass
class Outcome:
    """What happened, or would happen, to one CSV row."""

    row: SeedRow
    status: str
    detail: str = ""
    bedrooms_created: int = 0
    size_created: int = 0


@dataclass
class Plan:
    eligible: list[SeedRow] = field(default_factory=list)
    blocked: list[Outcome] = field(default_factory=list)


def normalize_header(name: str) -> str:
    return (name or "").strip().lower().replace(" ", "_").replace("-", "_")


def read_csv(path: Path) -> list[SeedRow]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            header = [normalize_header(cell) for cell in next(reader)]
        except StopIteration:
            raise CsvError(f"{path.name} is empty")

        def column_for(candidates: frozenset[str], label: str) -> int:
            found = [index for index, name in enumerate(header) if name in candidates]
            if not found:
                raise CsvError(
                    f"{path.name}: no {label} column "
                    f"(looked for {', '.join(sorted(candidates))}; got {', '.join(header)})"
                )
            if len(found) > 1:
                raise CsvError(f"{path.name}: more than one {label} column")
            return found[0]

        target_index = column_for(TARGET_ID_HEADERS, "target market id")
        slug_index = column_for(SLUG_HEADERS, "market slug")
        source_index = column_for(SOURCE_ID_HEADERS, "lookalike market id")

        rows: list[SeedRow] = []
        for line, cells in enumerate(reader, start=2):
            if not any(cell.strip() for cell in cells):
                continue

            def cell(index: int) -> str:
                return cells[index].strip() if index < len(cells) else ""

            def as_id(index: int, label: str) -> int:
                raw = cell(index)
                if not raw:
                    raise CsvError(f"{path.name} line {line}: {label} is empty")
                try:
                    return int(raw)
                except ValueError:
                    raise CsvError(f"{path.name} line {line}: {label} '{raw}' is not an integer")

            slug = cell(slug_index)
            if not slug:
                raise CsvError(f"{path.name} line {line}: market_slug is empty")
            rows.append(
                SeedRow(
                    line=line,
                    target_id=as_id(target_index, "id"),
                    market_slug=slug,
                    source_id=as_id(source_index, "lookalike market id"),
                )
            )

    duplicates = sorted(
        {row.target_id for row in rows if [r.target_id for r in rows].count(row.target_id) > 1}
    )
    if duplicates:
        raise CsvError(
            f"{path.name}: target market id listed more than once: "
            f"{', '.join(str(target_id) for target_id in duplicates)}"
        )
    return rows


async def build_plan(session, rows: list[SeedRow]) -> Plan:
    """Classify every row without writing anything.

    Mirrors the service's refusals so a dry run shows the same verdicts the
    commit pass will produce. The service remains the authority -- anything that
    changes between the two passes surfaces as a refusal there, not a bad write.
    """
    markets = {
        market.id: market
        for market in (
            await session.execute(
                select(MarketKeysMaster).where(MarketKeysMaster.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    }
    bedrooms_repo = OpexByBedroomsRepository(session)
    size_repo = OpexBySizeRepository(session)

    mismatches = [
        f"line {row.line}: id {row.target_id} is "
        f"'{markets[row.target_id].market_slug}', CSV says '{row.market_slug}'"
        for row in rows
        if row.target_id in markets and markets[row.target_id].market_slug != row.market_slug
    ]
    if mismatches:
        raise CsvError(
            "id/slug disagree with market_keys_master — the CSV is stale:\n  "
            + "\n  ".join(mismatches)
        )

    plan = Plan()
    for row in rows:
        target = markets.get(row.target_id)
        source = markets.get(row.source_id)
        if target is None:
            plan.blocked.append(Outcome(row, "missing target", f"market {row.target_id} not found"))
            continue
        if source is None:
            plan.blocked.append(
                Outcome(row, "missing lookalike", f"market {row.source_id} not found")
            )
            continue
        if row.target_id == row.source_id:
            plan.blocked.append(Outcome(row, "same market", "target is its own lookalike"))
            continue

        status = (target.market_status or "").strip().lower()
        if status != MarketStatus.EXPLORATORY:
            plan.blocked.append(
                Outcome(row, "not exploratory", f"market_status '{target.market_status}'")
            )
            continue

        occupied = [
            name
            for name, existing in (
                ("opex_by_bedrooms", await bedrooms_repo.get_all_by_market(row.target_id)),
                ("opex_by_size", await size_repo.get_all_by_market(row.target_id)),
            )
            if existing
        ]
        if occupied:
            plan.blocked.append(Outcome(row, "already seeded", ", ".join(occupied)))
            continue

        empty = [
            name
            for name, existing in (
                ("opex_by_bedrooms", await bedrooms_repo.get_all_by_market(row.source_id)),
                ("opex_by_size", await size_repo.get_all_by_market(row.source_id)),
            )
            if not existing
        ]
        if empty:
            plan.blocked.append(
                Outcome(row, "lookalike empty", f"{row.source_id} has no {', '.join(empty)}")
            )
            continue

        plan.eligible.append(row)

    return plan


async def seed_one(row: SeedRow) -> Outcome:
    """One market, one session, one transaction — the same unit as one API call."""
    async with AsyncSessionLocal() as session:
        service = OpexSeedService(
            session,
            OpexByBedroomsRepository(session),
            OpexBySizeRepository(session),
            MarketRepository(session),
        )
        try:
            result = await service.seed_from_lookalike(
                target_market_id=row.target_id,
                source_market_id=row.source_id,
            )
        except OpexSeedError as error:
            return Outcome(row, "refused", str(error))
        except ValueError as error:
            return Outcome(row, "refused", str(error))
        except Exception as error:  # noqa: BLE001 — one bad market must not stop the batch
            return Outcome(row, "failed", f"{type(error).__name__}: {error}")
        return Outcome(
            row,
            "seeded",
            bedrooms_created=result.bedrooms_created,
            size_created=result.size_created,
        )


def print_blocked(blocked: list[Outcome]) -> None:
    by_status: dict[str, list[Outcome]] = defaultdict(list)
    for outcome in blocked:
        by_status[outcome.status].append(outcome)
    for status, outcomes in sorted(by_status.items()):
        print(f"\n  SKIPPED — {status} ({len(outcomes)}):")
        for outcome in sorted(outcomes, key=lambda o: o.row.line):
            print(f"    {outcome.row}: {outcome.detail}")


async def run(path: Path, *, commit: bool, only: set[int] | None, verbose: bool) -> int:
    rows = read_csv(path)
    if only is not None:
        unknown = only - {row.target_id for row in rows}
        if unknown:
            raise CsvError(
                f"--only names market ids not in {path.name}: "
                f"{', '.join(str(target_id) for target_id in sorted(unknown))}"
            )
        rows = [row for row in rows if row.target_id in only]
    print(f"{path.name}: {len(rows)} market(s) to consider")

    async with AsyncSessionLocal() as session:
        plan = await build_plan(session, rows)

    if verbose and plan.eligible:
        print(f"\n  TO SEED ({len(plan.eligible)}):")
        for row in plan.eligible:
            print(f"    {row}")
    print_blocked(plan.blocked)

    if not commit:
        print(
            f"\nDRY RUN — nothing written. "
            f"{len(plan.eligible)} market(s) would be seeded, {len(plan.blocked)} skipped."
            f"\nRe-run with --commit to apply."
        )
        return 1 if plan.blocked else 0

    print(f"\nSeeding {len(plan.eligible)} market(s)...")
    outcomes = [await seed_one(row) for row in plan.eligible]
    seeded = [outcome for outcome in outcomes if outcome.status == "seeded"]
    problems = [outcome for outcome in outcomes if outcome.status != "seeded"]

    if verbose:
        for outcome in seeded:
            print(
                f"    {outcome.row}: {outcome.bedrooms_created} bedrooms row(s), "
                f"{outcome.size_created} size row(s)"
            )
    if problems:
        print_blocked(problems)

    print(
        f"\nSeeded {len(seeded)} market(s): "
        f"{sum(outcome.bedrooms_created for outcome in seeded)} opex_by_bedrooms row(s), "
        f"{sum(outcome.size_created for outcome in seeded)} opex_by_size row(s)."
    )
    skipped = len(plan.blocked) + len(problems)
    if skipped:
        print(f"{skipped} market(s) not seeded — see above.")
    return 1 if skipped else 0


def parse_only(value: str | None) -> set[int] | None:
    if value is None:
        return None
    try:
        return {int(part) for part in value.replace(",", " ").split()}
    except ValueError:
        raise CsvError(f"--only expects comma-separated market ids, got '{value}'")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help=f"defaults to {DEFAULT_CSV.name}")
    parser.add_argument("--commit", action="store_true", help="write the rows (default: dry run)")
    parser.add_argument("--only", help="comma-separated target market ids to limit the run to")
    parser.add_argument("--quiet", action="store_true", help="summary only, no per-market lines")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"ERROR: {args.csv} not found", file=sys.stderr)
        return 2

    try:
        return asyncio.run(
            run(args.csv, commit=args.commit, only=parse_only(args.only), verbose=not args.quiet)
        )
    except CsvError as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
