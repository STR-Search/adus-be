"""Clear iron_bank.underwritings.property_pending on deals whose listing is OTHER.

``home_status = 'OTHER'`` used to count as pending; it now counts as not pending,
alongside FOR_SALE (see ``NOT_PENDING_HOME_STATUSES`` in
``underwriting_repository``). Rows saved or synced under the old rule still hold
``property_pending = true``. This flips exactly those rows to false and touches
nothing else.

The next ``bulk_sync_property_pending`` run (``run_uw_auto_prepare.py
--since-hours``) would reach the same rows. This script exists to apply the
change on its own, scoped to OTHER, without running the rest of the batch.

Runs as one set-based UPDATE joined on zpid. Idempotent: only rows whose flag is
not already false are candidates, so re-running reports zero updates. NULL flags
on OTHER listings are written as false too, which is what the sync would do.

Usage:
  uv run python scripts/backfill_underwriting_property_pending_other.py --dry-run
  uv run python scripts/backfill_underwriting_property_pending_other.py
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parent.parent))

# Every underwriting whose listing is OTHER, by its current flag value.
REPORT_SQL = """
SELECT
    count(*) AS other_listing_rows,
    count(*) FILTER (WHERE uw.property_pending IS TRUE) AS currently_pending,
    count(*) FILTER (WHERE uw.property_pending IS NULL) AS currently_null,
    count(*) FILTER (WHERE uw.property_pending IS FALSE) AS already_not_pending
FROM iron_bank.underwritings uw
JOIN zillow.scheduled_listings sl ON sl.zpid = uw.zpid
WHERE sl.home_status = 'OTHER'
"""

# IS DISTINCT FROM false catches both true and NULL, and keeps rowcount equal to
# the number of rows that actually change.
UPDATE_SQL = """
UPDATE iron_bank.underwritings AS uw
SET property_pending = false
FROM zillow.scheduled_listings AS sl
WHERE uw.zpid = sl.zpid
  AND sl.home_status = 'OTHER'
  AND uw.property_pending IS DISTINCT FROM false
"""

# The rows about to change, for eyeballing before a real run.
SAMPLE_SQL = """
SELECT uw.id, uw.zpid, uw.property_pending, uw.deal_status, uw.property_address
FROM iron_bank.underwritings uw
JOIN zillow.scheduled_listings sl ON sl.zpid = uw.zpid
WHERE sl.home_status = 'OTHER'
  AND uw.property_pending IS DISTINCT FROM false
ORDER BY uw.id
LIMIT 10
"""


async def run(*, dry_run: bool) -> dict[str, Any]:
    from sqlalchemy import text

    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        report = dict((await session.execute(text(REPORT_SQL))).one()._mapping)
        sample = [
            dict(row._mapping)
            for row in (await session.execute(text(SAMPLE_SQL))).all()
        ]

        if dry_run:
            updated = 0
        else:
            result = await session.execute(text(UPDATE_SQL))
            updated = result.rowcount
            await session.commit()

    return {
        "dry_run": dry_run,
        **report,
        "to_update": report["currently_pending"] + report["currently_null"],
        "updated": updated,
        "sample_to_update": sample,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing",
    )
    args = parser.parse_args()

    report = asyncio.run(run(dry_run=args.dry_run))
    print(json.dumps(report, indent=2, default=str))

    if not report["dry_run"] and report["updated"] != report["to_update"]:
        print(
            f"WARNING: updated {report['updated']} rows but "
            f"{report['to_update']} were candidates — the data changed under "
            "the run. Re-run to reconcile."
        )


if __name__ == "__main__":
    main()
