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
from app.markets.models import OpexBySize

DATA_DIR = Path(__file__).resolve().parent / "data"
CSV_FILE = DATA_DIR / "f-opex_by_size.csv"
SLUG_MAP_FILE = DATA_DIR / "slug_mapping.json"


def _decimal(val: str) -> Decimal | None:
    v = val.strip()
    return Decimal(v) if v else None


def load_rows():
    with open(SLUG_MAP_FILE, encoding="utf-8") as f:
        slug_map: dict[str, str] = json.load(f)

    rows = []
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [h.strip() for h in reader.fieldnames]
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
                    "sqft": int(row["SQFT"].strip()) if row["SQFT"].strip() else None,
                    "internet": _decimal(row["Internet"]),
                    "pest_control": _decimal(row["Pest Control"]),
                    "utilities": _decimal(row["Utilities"]),
                }
            )
    return rows


async def seed():
    rows = load_rows()
    if not rows:
        print("No rows loaded from CSV.")
        return

    async with AsyncSessionLocal() as session:
        markets = (await session.execute(select(MarketKeysMaster))).scalars().all()
        slug_to_id = {m.market_slug: m.id for m in markets}

        missing_slugs = {r["_slug"] for r in rows if r["_slug"] not in slug_to_id}
        if missing_slugs:
            for slug in sorted(missing_slugs):
                print(
                    f"  WARNING: slug '{slug}' not found in market_keys_master — rows for this market will be skipped"
                )

        existing = (await session.execute(select(OpexBySize))).scalars().all()
        existing_keys = {(r.market_id, r.sqft) for r in existing}

        to_insert = []
        for row in rows:
            market_id = slug_to_id.get(row["_slug"])
            if market_id is None:
                continue
            if (market_id, row["sqft"]) in existing_keys:
                continue
            data = {k: v for k, v in row.items() if k != "_slug"}
            data["market_id"] = market_id
            to_insert.append(OpexBySize(**data))

        if not to_insert:
            print("Nothing to seed — all opex_by_size records already exist.")
            return

        session.add_all(to_insert)
        await session.commit()
        print(f"Seeded {len(to_insert)} opex_by_size record(s).")


if __name__ == "__main__":
    asyncio.run(seed())
