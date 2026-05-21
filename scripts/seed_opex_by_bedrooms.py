import asyncio
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.markets.models import MarketKeysMaster
from app.markets.models import OpexByBedrooms

DATA_DIR = Path(__file__).resolve().parent / "data"
CSV_FILE = DATA_DIR / "f-opex_by_bedrooms.csv"
SLUG_MAP_FILE = DATA_DIR / "slug_mapping.json"


def _currency(val: str) -> Decimal | None:
    v = val.strip().lstrip("$").replace(",", "")
    return Decimal(v) if v else None


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
                    "pool_hot_tub_low": _currency(row["Pool_HotTub_Low"]),
                    "pool_hot_tub_high": _currency(row["Pool_HotTub_High"]),
                    "outdoor_landscaping": _currency(row["Outdoor/Landscaping"]),
                    "software": _currency(row["Software"]),
                    "insurance_hoi": _currency(row["Insurance HOI"]),
                    "supplies": _currency(row["Supplies"]),
                    "capex_reserve": _currency(row["CapEx Reserve"]),
                    "cleaning_fee": _currency(row["Cleaning Fee"]),
                    "num_of_turns": (
                        Decimal(row["# of Turns"].strip())
                        if row["# of Turns"].strip()
                        else None
                    ),
                    "property_taxes": _percent(row["Property Taxes"]),
                    "land_value": _percent(row["Land_Value"]),
                    "appreciation": _percent(row["Appreciation"]),
                    "hoa_fees": _currency(row["HOA fees"]),
                    "furnishings_low": _currency(row["Furnishings_Low"]),
                    "furnishings_high": _currency(row["Furnishings_High"]),
                    "consolidated_shipping": _currency(row["Consolidated_Shipping"]),
                }
            )
    return rows


async def seed():
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

        existing = (await session.execute(select(OpexByBedrooms))).scalars().all()
        existing_keys = {(r.market_id, r.bedrooms) for r in existing}

        to_insert = []
        for row in rows:
            market_id = slug_to_id.get(row["_slug"])
            if market_id is None:
                continue
            if (market_id, row["bedrooms"]) in existing_keys:
                continue
            data = {k: v for k, v in row.items() if k != "_slug"}
            data["market_id"] = market_id
            to_insert.append(OpexByBedrooms(**data))

        if not to_insert:
            print("Nothing to seed — all opex_by_bedrooms records already exist.")
            return

        session.add_all(to_insert)
        await session.commit()
        print(f"Seeded {len(to_insert)} opex_by_bedrooms record(s).")


if __name__ == "__main__":
    asyncio.run(seed())
