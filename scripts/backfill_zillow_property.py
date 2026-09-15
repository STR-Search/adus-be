"""Backfill uw_details.zillow_property for legacy_sheet underwritings that
have no zpid but do have a listing_url, by calling the external Zillow
property-details API (ZillowPropertyService) directly -- the same client
used by the app's non-automated create/update flows.

Scope: source='legacy_sheet', zpid IS NULL, listing_url is a zillow.com URL,
and uw_details.zillow_property IS NULL (or uw_details doesn't exist yet).
Rows with no listing_url, or a listing_url on another site (Redfin,
Realtor.com, Airbnb, Google Drive, ...), have nothing this API can scrape
and are out of scope here.

Runs strictly sequentially, one request at a time -- the upstream API is a
real Zillow scrape and can rate-limit or block on bursts.

Usage:
  python scripts/backfill_zillow_property.py --dry-run --limit 5
  python scripts/backfill_zillow_property.py --limit 5
  python scripts/backfill_zillow_property.py
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

REPORT_PATH = Path(__file__).resolve().parent / "zillow_property_backfill_report.json"

# Keys ZillowPropertyService returns beyond the canonical ZillowProperty
# shape -- lifted onto the underwriting row's own columns elsewhere in the
# app (see non_automated_underwriting_payload_builder.py), never stored
# inside zillow_property itself. Popped here so this script's output
# matches the 11-key shape already on every existing row.
ADDRESS_PART_KEYS = ("street", "city", "state")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill uw_details.zillow_property for legacy deals with no "
            "zpid but a listing_url."
        )
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Only process the first N candidates."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Fetch and report only; no DB writes."
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds to sleep between requests (politeness on the upstream scrape).",
    )
    return parser.parse_args()


async def fetch_candidates(session, limit: int | None):
    from sqlalchemy import select

    from app.iron_bank.models import Underwriting, UnderwritingDetail

    stmt = (
        select(
            Underwriting.id,
            Underwriting.listing_url,
            Underwriting.market_id,
            Underwriting.sheet_number,
        )
        .outerjoin(
            UnderwritingDetail, UnderwritingDetail.underwriting_id == Underwriting.id
        )
        .where(
            Underwriting.source == "legacy_sheet",
            Underwriting.zpid.is_(None),
            Underwriting.listing_url.ilike("%zillow.com%"),
            UnderwritingDetail.zillow_property.is_(None),
        )
        .order_by(Underwriting.sheet_number)
    )
    if limit:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return result.all()


async def main() -> None:
    args = parse_args()

    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.external_api.services.zillow_property_service import (
        ZillowPropertyService,
    )
    from app.iron_bank.models import UnderwritingDetail

    service = ZillowPropertyService()
    updated: list[dict] = []
    empty: list[dict] = []
    failed: list[dict] = []

    async with AsyncSessionLocal() as session:
        candidates = await fetch_candidates(session, args.limit)
        print(f"{len(candidates)} candidate(s) to process")

        for i, (uid, url, market_id, sheet_number) in enumerate(candidates):
            print(
                f"[{i + 1}/{len(candidates)}] sheet_number={sheet_number} "
                f"underwriting_id={uid} url={url}"
            )
            try:
                zillow_property = await service.fetch_property_details(
                    url=url, market_id=market_id
                )
            except Exception as exc:
                print(f"  FAILED: {exc}")
                failed.append(
                    {
                        "underwriting_id": uid,
                        "sheet_number": sheet_number,
                        "error": str(exc),
                    }
                )
                continue

            if zillow_property is None:
                print("  EMPTY: no property returned")
                empty.append({"underwriting_id": uid, "sheet_number": sheet_number})
                continue

            for key in ADDRESS_PART_KEYS:
                zillow_property.pop(key, None)

            if not args.dry_run:
                detail = (
                    await session.execute(
                        select(UnderwritingDetail).where(
                            UnderwritingDetail.underwriting_id == uid
                        )
                    )
                ).scalar_one_or_none()
                if detail is None:
                    detail = UnderwritingDetail(
                        underwriting_id=uid, zillow_property=zillow_property
                    )
                    session.add(detail)
                else:
                    detail.zillow_property = zillow_property
                await session.commit()

            print(f"  OK: zpid={zillow_property.get('id')}")
            updated.append(
                {
                    "underwriting_id": uid,
                    "sheet_number": sheet_number,
                    "zpid_found": zillow_property.get("id"),
                }
            )

            if i < len(candidates) - 1:
                await asyncio.sleep(args.delay)

    report = {
        "dry_run": args.dry_run,
        "limit": args.limit,
        "updated": updated,
        "empty": empty,
        "failed": failed,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str))
    print(
        json.dumps(
            {"updated": len(updated), "empty": len(empty), "failed": len(failed)},
            indent=2,
        )
    )
    print(f"report -> {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
