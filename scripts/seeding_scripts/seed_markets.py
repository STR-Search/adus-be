import asyncio
import csv
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.markets.models import MarketKeysMaster

DATA_FILE = Path(__file__).resolve().parent / "data" / "f-markets.csv"


def load_markets():
    markets = []
    with open(DATA_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            markets.append(
                {
                    "market_slug": row["market_slug"].strip() or None,
                    "market_name": row["Market (New)"].strip() or None,
                    "market_name_current": row["Market (Current)"].strip() or None,
                    "market_status": row["Market_Status"].strip() or None,
                    "analyst_owner": row["Analyst_Owner"].strip() or None,
                }
            )
    return markets


async def seed():
    markets = load_markets()

    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(MarketKeysMaster))).scalars().all()
        existing_slugs = {m.market_slug for m in existing}

        to_insert = [
            MarketKeysMaster(**m)
            for m in markets
            if m["market_slug"] and m["market_slug"] not in existing_slugs
        ]

        if not to_insert:
            print("Nothing to seed — all markets already exist.")
            return

        session.add_all(to_insert)
        await session.commit()
        print(f"Seeded {len(to_insert)} market(s):")
        for m in to_insert:
            print(f"  {m.market_slug}")


if __name__ == "__main__":
    asyncio.run(seed())
