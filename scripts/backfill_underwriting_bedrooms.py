"""Backfill iron_bank.underwritings.bedrooms / .bathrooms from Zillow data.

Those two columns are the analyst-approved underwriting assumption and the key
for every post-creation opex_by_bedrooms lookup. Rows created before the
columns existed have them NULL, so this seeds them from whichever Zillow source
the row actually has:

1. uw_details.zillow_property (non-automated deals, including create-from-URL)
2. zillow.scheduled_listings via underwritings.zpid (automated deals)

Runs as one set-based UPDATE rather than a statement per row -- the whole
backfill is a single round trip.

Idempotent: COALESCE keeps any value already present, and the candidate set is
restricted to rows with a NULL column, so re-running reports zero updates.

Some rows are unresolvable by design -- source='legacy_sheet' deals were loaded
with is_automated=False, no stored zillow_property, and only sometimes a zpid
matched afterwards. They are counted as 'unresolved', not as failures; they
already render without furnishing prices today.

Usage:
  uv run python scripts/backfill_underwriting_bedrooms.py --dry-run
  uv run python scripts/backfill_underwriting_bedrooms.py
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parent.parent))

# Every candidate row with both Zillow sources resolved to typed values.
#
# DISTINCT ON guards the uw_details join: nothing in the schema enforces one
# detail row per underwriting (the only index is the PK), and a duplicate would
# otherwise make the UPDATE's choice of source arbitrary.
#
# The regex guards the casts. zillow_property is JSONB written from an external
# feed, so ->> can yield '4.0' or a non-numeric string; Postgres has no
# TRY_CAST, and an unguarded ::numeric would abort the whole statement. trunc()
# then matches Python's int(Decimal(...)) truncation, and round(_, 1) matches
# what the numeric(4,1) column would store anyway.
RESOLVED_CTE = r"""
WITH resolved AS (
    SELECT DISTINCT ON (u.id)
        u.id,
        u.bedrooms  AS current_bedrooms,
        u.bathrooms AS current_bathrooms,
        CASE
            WHEN d.zillow_property ->> 'bedrooms' ~ '^\s*[0-9]+(\.[0-9]+)?\s*$'
            THEN trunc((d.zillow_property ->> 'bedrooms')::numeric)::int
        END AS stored_bedrooms,
        CASE
            WHEN d.zillow_property ->> 'bathrooms' ~ '^\s*[0-9]+(\.[0-9]+)?\s*$'
            THEN round((d.zillow_property ->> 'bathrooms')::numeric, 1)
        END AS stored_bathrooms,
        l.beds AS listing_beds,
        round(l.baths::numeric, 1) AS listing_baths
    FROM iron_bank.underwritings u
    LEFT JOIN iron_bank.uw_details d ON d.underwriting_id = u.id
    LEFT JOIN zillow.scheduled_listings l ON l.zpid = u.zpid
    WHERE u.bedrooms IS NULL OR u.bathrooms IS NULL
    ORDER BY u.id, d.id
)
"""

# Which source would win for each field, so a --dry-run can be reviewed before
# anything is written. Mirrors the COALESCE order in UPDATE_SQL exactly.
REPORT_SQL = (
    RESOLVED_CTE
    + """
SELECT
    count(*) AS candidates,
    count(*) FILTER (
        WHERE current_bedrooms IS NULL AND stored_bedrooms IS NOT NULL
    ) AS bedrooms_from_zillow_property,
    count(*) FILTER (
        WHERE current_bedrooms IS NULL AND stored_bedrooms IS NULL
          AND listing_beds IS NOT NULL
    ) AS bedrooms_from_scheduled_listing,
    count(*) FILTER (
        WHERE current_bedrooms IS NULL AND stored_bedrooms IS NULL
          AND listing_beds IS NULL
    ) AS unresolved_bedrooms,
    count(*) FILTER (
        WHERE current_bathrooms IS NULL AND stored_bathrooms IS NOT NULL
    ) AS bathrooms_from_zillow_property,
    count(*) FILTER (
        WHERE current_bathrooms IS NULL AND stored_bathrooms IS NULL
          AND listing_baths IS NOT NULL
    ) AS bathrooms_from_scheduled_listing,
    count(*) FILTER (
        WHERE current_bathrooms IS NULL AND stored_bathrooms IS NULL
          AND listing_baths IS NULL
    ) AS unresolved_bathrooms,
    count(*) FILTER (
        WHERE COALESCE(current_bedrooms, stored_bedrooms, listing_beds) IS NOT NULL
           OR COALESCE(current_bathrooms, stored_bathrooms, listing_baths) IS NOT NULL
    ) AS resolvable
FROM resolved
"""
)

UPDATE_SQL = (
    RESOLVED_CTE
    + """
UPDATE iron_bank.underwritings u
SET bedrooms  = COALESCE(u.bedrooms, r.stored_bedrooms, r.listing_beds),
    bathrooms = COALESCE(u.bathrooms, r.stored_bathrooms, r.listing_baths)
FROM resolved r
WHERE u.id = r.id
  -- Skip rows nothing can resolve, so they are reported as unresolved rather
  -- than counted as no-op updates.
  AND (
        COALESCE(u.bedrooms, r.stored_bedrooms, r.listing_beds) IS NOT NULL
     OR COALESCE(u.bathrooms, r.stored_bathrooms, r.listing_baths) IS NOT NULL
  )
"""
)

# Rows no Zillow source can fill, grouped by provenance -- expected to be
# entirely source='legacy_sheet'. Anything else here is worth a look.
UNRESOLVED_BY_SOURCE_SQL = (
    RESOLVED_CTE
    + """
SELECT u.source, count(*) AS rows
FROM resolved r
JOIN iron_bank.underwritings u ON u.id = r.id
WHERE COALESCE(r.current_bedrooms, r.stored_bedrooms, r.listing_beds) IS NULL
  AND COALESCE(r.current_bathrooms, r.stored_bathrooms, r.listing_baths) IS NULL
GROUP BY u.source
ORDER BY rows DESC
"""
)


async def run(dry_run: bool) -> dict[str, Any]:
    from sqlalchemy import text

    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        report = dict(
            (await session.execute(text(REPORT_SQL))).one()._mapping
        )
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
            "were resolvable — the data changed under the run, or a duplicate "
            "uw_details row was collapsed. Re-run to reconcile."
        )


if __name__ == "__main__":
    main()
