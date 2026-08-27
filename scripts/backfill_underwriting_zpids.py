"""Backfill iron_bank.underwritings.zpid on deals that were saved without one.

Two populations have a NULL zpid: deals created through the create-from-URL
flow before the scrape began persisting listings (the property had no
zillow.scheduled_listings row to point the FK at), and -- far more numerous --
rows loaded by the legacy Google Sheet backfill, which set is_automated=False
and never resolved a zpid at all. On the dev snapshot this was 1,637 rows, of
which only 106 are recoverable and 101 of those are source='legacy_sheet'.

Those rows are invisible to every zpid-keyed job:

  * price reconciliation (UnderwritingRepository.get_all_by_zpid)
  * property_pending sync (bulk_sync_property_pending, joins on zpid)
  * the automated duplicate guard and list zillow enrichment

so they silently hold whatever purchase price they were created with, forever.

The zpid is recoverable from the stored listing URL -- Zillow homedetails URLs
end in /<zpid>_zpid/ -- but it can only be written when that zpid actually
exists in zillow.scheduled_listings, since the column is an FK. Properties that
were never scraped stay NULL and are reported as 'unresolved_not_scraped'.

Two candidate sources, in order:

1. underwritings.listing_url        -- the URL the analyst pasted
2. uw_details.zillow_property->>'id' -- the zpid the fetch returned, which the
                                        payload builder has always stored even
                                        while leaving the column NULL

Source 2 is the more reliable of the two (it is the zpid Zillow itself
returned), so it is preferred; the URL regex is the fallback for rows predating
the stored blob. On the dev snapshot the blob resolved all 106 and the regex
contributed none -- it is kept as a cheap guard for rows that carry a URL but
no stored property, not because it is currently pulling weight.

Runs as one set-based UPDATE. Idempotent: only rows with a NULL zpid are
candidates, so re-running reports zero updates.

IMPORTANT -- this does NOT merge anything. Most recoverable rows will end up
sharing a zpid with an existing automated deal for the same property. That is
legal (zpid is not unique) and is what makes reconciliation reach them, but the
two rows remain separate series and will still show as two deals at one
address. Merging series is a separate, product-level decision; --report-only
prints how many rows are in that position so it can be sized first.

Usage:
  uv run python scripts/backfill_underwriting_zpids.py --dry-run
  uv run python scripts/backfill_underwriting_zpids.py --report-only
  uv run python scripts/backfill_underwriting_zpids.py
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parent.parent))

# Every NULL-zpid candidate with its recoverable zpid resolved, and whether that
# zpid is FK-satisfiable.
#
# DISTINCT ON guards the uw_details join: nothing in the schema enforces one
# detail row per underwriting (the only index is the PK), so a duplicate would
# otherwise make the UPDATE's choice of source arbitrary.
#
# The regex is anchored to the _zpid/ suffix Zillow uses; a URL that doesn't
# match yields NULL rather than a wrong id. The digits are kept as text because
# the column and the FK target are both text.
RESOLVED_CTE = r"""
WITH resolved AS (
    SELECT DISTINCT ON (u.id)
        u.id,
        u.source,
        u.is_automated,
        COALESCE(
            NULLIF(d.zillow_property ->> 'id', ''),
            substring(u.listing_url FROM '/([0-9]+)_zpid')
        ) AS candidate_zpid
    FROM iron_bank.underwritings u
    LEFT JOIN iron_bank.uw_details d ON d.underwriting_id = u.id
    WHERE u.zpid IS NULL
    ORDER BY u.id, d.id
),
classified AS (
    SELECT
        r.*,
        (sl.zpid IS NOT NULL) AS is_scraped,
        EXISTS (
            SELECT 1 FROM iron_bank.underwritings other
            WHERE other.zpid = r.candidate_zpid
        ) AS shares_with_existing
    FROM resolved r
    LEFT JOIN zillow.scheduled_listings sl ON sl.zpid = r.candidate_zpid
)
"""

REPORT_SQL = (
    RESOLVED_CTE
    + """
SELECT
    count(*) AS null_zpid_rows,
    count(*) FILTER (WHERE candidate_zpid IS NULL) AS unresolved_no_candidate,
    count(*) FILTER (
        WHERE candidate_zpid IS NOT NULL AND NOT is_scraped
    ) AS unresolved_not_scraped,
    count(*) FILTER (WHERE is_scraped) AS resolvable,
    count(*) FILTER (
        WHERE is_scraped AND shares_with_existing
    ) AS resolvable_sharing_zpid_with_existing_deal
FROM classified
"""
)

UPDATE_SQL = (
    RESOLVED_CTE
    + """
UPDATE iron_bank.underwritings u
SET zpid = c.candidate_zpid
FROM classified c
WHERE u.id = c.id
  -- is_scraped is the FK guard: without it the statement aborts on the first
  -- property that was never scraped, taking the whole backfill with it.
  AND c.is_scraped
  AND u.zpid IS NULL
"""
)

# What is left behind, by provenance. Expected to be dominated by deals whose
# property was never scraped; anything unexpected here is worth a look before
# assuming the backfill is complete.
UNRESOLVED_BY_SOURCE_SQL = (
    RESOLVED_CTE
    + """
SELECT
    COALESCE(source, 'unknown') AS source,
    CASE WHEN candidate_zpid IS NULL THEN 'no_candidate_zpid'
         ELSE 'not_in_scheduled_listings' END AS reason,
    count(*) AS rows
FROM classified
WHERE NOT is_scraped
GROUP BY 1, 2
ORDER BY rows DESC
"""
)

# The rows about to change, for eyeballing before a real run.
SAMPLE_SQL = (
    RESOLVED_CTE
    + """
SELECT c.id, c.candidate_zpid, c.shares_with_existing, u.listing_url
FROM classified c
JOIN iron_bank.underwritings u ON u.id = c.id
WHERE c.is_scraped
ORDER BY c.id
LIMIT 10
"""
)


async def run(*, dry_run: bool, report_only: bool) -> dict[str, Any]:
    from sqlalchemy import text

    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        report = dict((await session.execute(text(REPORT_SQL))).one()._mapping)
        unresolved = [
            dict(row._mapping)
            for row in (await session.execute(text(UNRESOLVED_BY_SOURCE_SQL))).all()
        ]
        sample = [
            dict(row._mapping)
            for row in (await session.execute(text(SAMPLE_SQL))).all()
        ]

        if dry_run or report_only:
            updated = 0
        else:
            result = await session.execute(text(UPDATE_SQL))
            updated = result.rowcount
            await session.commit()

    return {
        "dry_run": dry_run,
        "report_only": report_only,
        **report,
        "updated": updated,
        "unresolved_by_source": unresolved,
        "sample_to_update": sample,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="counts only, no write — same as --dry-run, named for prod runbooks",
    )
    args = parser.parse_args()

    report = asyncio.run(run(dry_run=args.dry_run, report_only=args.report_only))
    print(json.dumps(report, indent=2, default=str))

    if report["dry_run"] or report["report_only"]:
        return

    if report["updated"] != report["resolvable"]:
        print(
            f"WARNING: updated {report['updated']} rows but "
            f"{report['resolvable']} were resolvable — the data changed under "
            "the run, or a duplicate uw_details row was collapsed. Re-run to "
            "reconcile."
        )
    if report["resolvable_sharing_zpid_with_existing_deal"]:
        print(
            f"NOTE: {report['resolvable_sharing_zpid_with_existing_deal']} "
            "backfilled rows now share a zpid with an existing deal for the "
            "same property. Reconciliation will reach both, but they remain "
            "separate series — merging them is a separate decision."
        )


if __name__ == "__main__":
    main()
