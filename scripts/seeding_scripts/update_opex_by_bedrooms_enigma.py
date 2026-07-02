"""Temporary script: update a subset of opex_by_bedrooms columns from
enigma_master_sheet11.csv.

Uses (Market, Bedrooms) to locate the unique existing row and updates only:
    property_taxes, furnishings_low, furnishings_mid, furnishings_high,
    consolidated_shipping

Rows whose market/bedrooms combination does not already exist are skipped
(this script updates only — it does not insert).
"""

import asyncio
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.markets.models import MarketKeysMaster
from app.markets.models import OpexByBedrooms

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CSV_FILE = DATA_DIR / "enigma_master_sheet11.csv"
SLUG_MAP_FILE = DATA_DIR / "slug_mapping.json"


def _currency(val: str) -> Decimal | None:
    # Handles a leading sign and "$"/"," anywhere (e.g. "-$5,000").
    v = val.strip().replace("$", "").replace(",", "")
    if not v:
        return None
    d = Decimal(v)
    # Negative currency values are treated as 0.
    return d if d > 0 else Decimal(0)


def _percent(val: str) -> Decimal | None:
    v = val.strip().rstrip("%")
    return Decimal(v) / 100 if v else None


def load_rows():
    with open(SLUG_MAP_FILE, encoding="utf-8") as f:
        slug_map: dict[str, str] = json.load(f)

    rows = []
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            market_name = row["Market"].strip()
            slug = slug_map.get(market_name)
            if not slug:
                print(
                    f"  WARNING: no slug mapping for market '{market_name}' — skipping row"
                )
                continue

            rows.append(
                {
                    "_slug": slug,
                    "bedrooms": (
                        int(row["Bedrooms"].strip())
                        if row["Bedrooms"].strip()
                        else None
                    ),
                    "property_taxes": _percent(row["Property Taxes"]),
                    "furnishings_low": _currency(row["Furnishings_Low"]),
                    "furnishings_mid": _currency(row["Furnishings_Mid"]),
                    "furnishings_high": _currency(row["Furnishings_High"]),
                    "consolidated_shipping": _currency(row["Consolidated_Shipping"]),
                }
            )
    return rows


# Columns this script is allowed to update.
UPDATE_FIELDS = (
    "property_taxes",
    "furnishings_low",
    "furnishings_mid",
    "furnishings_high",
    "consolidated_shipping",
)


async def update():
    rows = load_rows()
    if not rows:
        print("No rows loaded from CSV.")
        return

    async with AsyncSessionLocal() as session:
        # Build slug → market_id lookup from DB
        markets = (await session.execute(select(MarketKeysMaster))).scalars().all()
        slug_to_id = {m.market_slug: m.id for m in markets}

        missing_slugs = {r["_slug"] for r in rows if r["_slug"] not in slug_to_id}
        if missing_slugs:
            for slug in sorted(missing_slugs):
                print(
                    f"  WARNING: slug '{slug}' not found in market_keys_master — rows for this market will be skipped"
                )

        # (market_id, bedrooms) → OpexByBedrooms instance
        existing = (await session.execute(select(OpexByBedrooms))).scalars().all()
        by_key = {(r.market_id, r.bedrooms): r for r in existing}

        updated = 0
        skipped = 0
        for row in rows:
            market_id = slug_to_id.get(row["_slug"])
            if market_id is None:
                skipped += 1
                continue

            record = by_key.get((market_id, row["bedrooms"]))
            if record is None:
                print(
                    f"  WARNING: no opex_by_bedrooms row for slug '{row['_slug']}' "
                    f"(market_id={market_id}), bedrooms={row['bedrooms']} — skipping"
                )
                skipped += 1
                continue

            for field in UPDATE_FIELDS:
                setattr(record, field, row[field])
            updated += 1

        if not updated:
            print(f"Nothing to update ({skipped} row(s) skipped).")
            return

        await session.commit()
        print(f"Updated {updated} opex_by_bedrooms record(s); {skipped} skipped.")


if __name__ == "__main__":
    asyncio.run(update())
