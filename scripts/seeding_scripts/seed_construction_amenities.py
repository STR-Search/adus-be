import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.markets.models import ConstructionCostsAmenities

AMENITIES = [
    ("Hot Tub", Decimal("14000"), Decimal("15500"), Decimal("17500")),
    ("Fire Pit", Decimal("3000"), Decimal("7000"), Decimal("15000")),
    ("Sauna", Decimal("14000"), Decimal("15500"), Decimal("17500")),
    (
        "Above Ground Pool WITH Deck",
        Decimal("40000"),
        Decimal("50000"),
        Decimal("52500"),
    ),
    ("Inground Pool", Decimal("100000"), Decimal("135000"), Decimal("175000")),
    ("Mini Golf", Decimal("5000"), Decimal("10000"), Decimal("30000")),
    ("Game Room", Decimal("7500"), Decimal("12500"), Decimal("20000")),
    ("Pickleball Court", Decimal("25000"), Decimal("35000"), Decimal("50000")),
    ("Basketball Court", Decimal("20000"), Decimal("25000"), Decimal("30000")),
    ("String Lights", Decimal("1000"), Decimal("3500"), Decimal("10000")),
    ("Play Ground", Decimal("3500"), Decimal("8500"), Decimal("15000")),
    ("Turf/Sod", Decimal("10000"), Decimal("25000"), Decimal("40000")),
]


async def seed():
    async with AsyncSessionLocal() as session:
        existing = (
            (await session.execute(select(ConstructionCostsAmenities))).scalars().all()
        )
        existing_names = {r.amenity_name for r in existing}

        to_insert = [
            ConstructionCostsAmenities(
                amenity_name=name,
                price_tier_1=tier1,
                price_tier_2=tier2,
                price_tier_3=tier3,
            )
            for name, tier1, tier2, tier3 in AMENITIES
            if name not in existing_names
        ]

        if not to_insert:
            print("Nothing to seed — all amenities already exist.")
            return

        session.add_all(to_insert)
        await session.commit()
        print(f"Seeded {len(to_insert)} amenity record(s):")
        for r in to_insert:
            print(f"  {r.amenity_name}")


if __name__ == "__main__":
    asyncio.run(seed())
