import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.markets.models import ConstructionCostsRemodeling

REMODELING = [
    ("Flooring", "sqft", Decimal("12"), Decimal("15"), Decimal("20")),
    ("Exterior Painting", "sqft", Decimal("4"), Decimal("6"), Decimal("8")),
    ("Interior Painting", "sqft", Decimal("4"), Decimal("5"), Decimal("6")),
    ("Accent Wall Paint", "number of", Decimal("400"), Decimal("600"), Decimal("1000")),
    ("Wallpaper", "number of", Decimal("1000"), Decimal("1500"), Decimal("2000")),
    ("Decking", "sqft", Decimal("35"), Decimal("45"), Decimal("55")),
    ("Fence", "sqft", Decimal("35"), Decimal("50"), Decimal("65")),
    ("Interior Doors", "number of", Decimal("350"), Decimal("500"), Decimal("700")),
    ("Ring Cameras", "number of", Decimal("500"), Decimal("750"), Decimal("1000")),
    ("Schlage Door Lock", "number of", Decimal("500"), Decimal("500"), Decimal("500")),
    ("Mini Splits", "number of", Decimal("4500"), Decimal("6500"), Decimal("10000")),
    ("Pool Automation", "static", Decimal("2500"), Decimal("2500"), Decimal("2500")),
]


async def seed():
    async with AsyncSessionLocal() as session:
        existing = (
            (await session.execute(select(ConstructionCostsRemodeling))).scalars().all()
        )
        existing_items = {r.rehab_item for r in existing}

        to_insert = [
            ConstructionCostsRemodeling(
                rehab_item=rehab_item,
                metric=metric,
                price_tier_1=tier1,
                price_tier_2=tier2,
                price_tier_3=tier3,
            )
            for rehab_item, metric, tier1, tier2, tier3 in REMODELING
            if rehab_item not in existing_items
        ]

        if not to_insert:
            print("Nothing to seed — all remodeling items already exist.")
            return

        session.add_all(to_insert)
        await session.commit()
        print(f"Seeded {len(to_insert)} remodeling record(s):")
        for r in to_insert:
            print(f"  {r.rehab_item}")


if __name__ == "__main__":
    asyncio.run(seed())
