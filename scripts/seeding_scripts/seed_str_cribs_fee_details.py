import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.markets.models import StrCribsFeeDetails

# Cribs fee tiers keyed by the inclusive upper bound (sqft) of each tier.
# The open-ended "4,000+" tier uses a max-int32 sentinel so a
# `sqft >= :area ORDER BY sqft LIMIT 1` lookup always resolves to a row.
SENTINEL_SQFT = 2147483647

ROWS = [
    {"sqft": 1000, "fee": Decimal("17500")},
    {"sqft": 2500, "fee": Decimal("25000")},
    {"sqft": 3500, "fee": Decimal("28000")},
    {"sqft": 4000, "fee": Decimal("30000")},
    {"sqft": SENTINEL_SQFT, "fee": Decimal("35000")},
]


async def seed():
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(StrCribsFeeDetails))).scalars().all()
        existing_sqft = {r.sqft for r in existing}

        to_insert = [
            StrCribsFeeDetails(**row)
            for row in ROWS
            if row["sqft"] not in existing_sqft
        ]

        if not to_insert:
            print("Nothing to seed — all str_cribs_fee_details records already exist.")
            return

        session.add_all(to_insert)
        await session.commit()
        print(f"Seeded {len(to_insert)} str_cribs_fee_details record(s).")


if __name__ == "__main__":
    asyncio.run(seed())
