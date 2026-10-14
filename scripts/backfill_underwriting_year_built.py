"""Backfill uw_details.zillow_property.year_built from the scraped listing.

Non-automated deals (create-from-URL) store a snapshot of the Zillow property
on uw_details.zillow_property and read it back from there. year_built was added
to that snapshot after those rows were written, so they display it as null.
Automated deals need nothing: they hydrate live from
zillow.scheduled_listing_details on every read.

This only affects what the detail/list payloads *show*. The year-built list
filter reads zillow.scheduled_listing_details directly by zpid and works for
these rows with or without this backfill.

Source is zillow.scheduled_listing_details joined on underwritings.zpid, so no
external API calls are made. Runs as one set-based UPDATE.

Idempotent: only snapshots whose year_built is absent or JSON null are
candidates, and only non-null values are written, so re-running reports zero
updates.

Some rows are unresolvable by design and are reported, not treated as failures:
- no zpid: blank / legacy_sheet deals, and URL deals created before the scrape
  persisted listings
- no listing details row, or one with a NULL year_built

Usage:
  uv run python scripts/backfill_underwriting_year_built.py --dry-run
  uv run python scripts/backfill_underwriting_year_built.py
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parent.parent))

# Every stored snapshot missing year_built, alongside what the listing has.
#
# jsonb_typeof guards the merge: ``||`` on a non-object (a JSON null or array
# written by some older path) would build an array rather than add a key.
# ->> 'year_built' IS NULL covers both an absent key and an explicit null, the
# latter being what the blank and create-from-URL paths now write when Zillow
# has no value.
CANDIDATES_CTE = """
WITH candidates AS (
    SELECT
        d.id AS detail_id,
        u.zpid,
        u.source,
        sld.year_built AS listing_year_built
    FROM iron_bank.underwritings u
    JOIN iron_bank.uw_details d ON d.underwriting_id = u.id
    LEFT JOIN zillow.scheduled_listing_details sld ON sld.zpid = u.zpid
    WHERE u.is_automated IS NOT TRUE
      AND jsonb_typeof(d.zillow_property) = 'object'
      AND d.zillow_property ->> 'year_built' IS NULL
)
"""

REPORT_SQL = (
    CANDIDATES_CTE
    + """
SELECT
    count(*) AS candidates,
    count(*) FILTER (WHERE listing_year_built IS NOT NULL) AS resolvable,
    count(*) FILTER (WHERE zpid IS NULL) AS unresolved_no_zpid,
    count(*) FILTER (
        WHERE zpid IS NOT NULL AND listing_year_built IS NULL
    ) AS unresolved_no_listing_value
FROM candidates
"""
)

UPDATE_SQL = (
    CANDIDATES_CTE
    + """
UPDATE iron_bank.uw_details d
SET zillow_property = d.zillow_property
    || jsonb_build_object('year_built', c.listing_year_built)
FROM candidates c
WHERE d.id = c.detail_id
  AND c.listing_year_built IS NOT NULL
"""
)

# Rows without a zpid, grouped by provenance -- expected to be blank and
# legacy_sheet deals plus early URL deals. Anything else is worth a look.
UNRESOLVED_BY_SOURCE_SQL = (
    CANDIDATES_CTE
    + """
SELECT source, count(*) AS rows
FROM candidates
WHERE listing_year_built IS NULL
GROUP BY source
ORDER BY rows DESC
"""
)


async def run(dry_run: bool) -> dict[str, Any]:
    from sqlalchemy import text

    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        report = dict((await session.execute(text(REPORT_SQL))).one()._mapping)
        unresolved_by_source = {
            row.source or "unknown": row.rows
            for row in (await session.execute(text(UNRESOLVED_BY_SOURCE_SQL))).all()
        }

        if dry_run:
            updated = 0
        else:
            result = await session.execute(text(UPDATE_SQL))
            updated = result.rowcount
            await session.commit()

    return {
        "dry_run": dry_run,
        **report,
        "updated": updated,
        "unresolved_by_source": unresolved_by_source,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing",
    )
    args = parser.parse_args()

    report = asyncio.run(run(args.dry_run))
    print(json.dumps(report, indent=2, default=str))

    if not report["dry_run"] and report["updated"] != report["resolvable"]:
        print(
            f"WARNING: updated {report['updated']} rows but {report['resolvable']} "
            "were resolvable — the data changed under the run. Re-run to reconcile."
        )


if __name__ == "__main__":
    main()
