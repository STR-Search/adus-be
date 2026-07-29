"""Temporary script: update market_keys_master amenity lists and analyst
owner from 'Enigma-Master - markets.csv'.

Matches rows on market_slug and updates only:
    must_have_amenities, nice_to_have_amenities, analyst_owner

Amenity labels are mapped to markets.construction_costs_amenities ids via
LABEL_TO_ID. Per agreed seeding decisions: "Pool" maps to id 4 (Above Ground
Pool WITH Deck) and "Gym" has no lookup row — unknown labels are skipped with
a warning. Empty amenity cells set the column to NULL. Rows whose slug does
not exist in the DB are skipped (this script updates only — it does not
insert).
"""

import asyncio
import csv
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.markets.models import MarketKeysMaster
from app.markets.models.construction import ConstructionCostsAmenities

CSV_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "scratch_pad"
    / "Enigma-Master - markets.csv"
)

# CSV label → construction_costs_amenities.id
LABEL_TO_ID = {
    "hot tub": 1,
    "fire pit": 2,
    "sauna": 3,
    "pool": 4,  # Above Ground Pool WITH Deck, per seeding decision
    "mini golf": 6,
    "game room": 7,
    "pickleball": 8,
    "playground": 11,
}


def _parse_amenities(cell: str, slug: str, column: str) -> list[int] | None:
    labels = [label.strip() for label in cell.split(",") if label.strip()]
    if not labels:
        return None
    ids = []
    for label in labels:
        amenity_id = LABEL_TO_ID.get(label.lower())
        if amenity_id is None:
            print(
                f"  WARNING: no amenity mapping for '{label}' "
                f"({column}, slug '{slug}') — skipping label"
            )
            continue
        ids.append(amenity_id)
    return ids or None


def load_rows() -> list[dict]:
    rows = []
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            slug = row["market_slug"].strip()
            if not slug:
                continue
            rows.append(
                {
                    "_slug": slug,
                    "must_have_amenities": _parse_amenities(
                        row["Must_Have_Amenities"], slug, "Must_Have_Amenities"
                    ),
                    "nice_to_have_amenities": _parse_amenities(
                        row["Nice_to_Have_Amenities"], slug, "Nice_to_Have_Amenities"
                    ),
                    "analyst_owner": row["Analyst_Owner"].strip() or None,
                }
            )
    return rows


async def update():
    rows = load_rows()
    if not rows:
        print("No rows loaded from CSV.")
        return

    async with AsyncSessionLocal() as session:
        # Sanity check: every mapped id must exist and be active in the lookup table.
        active_ids = set(
            (
                await session.execute(
                    select(ConstructionCostsAmenities.id).where(
                        ConstructionCostsAmenities.deleted_at.is_(None)
                    )
                )
            ).scalars()
        )
        stale = set(LABEL_TO_ID.values()) - active_ids
        if stale:
            print(f"ERROR: LABEL_TO_ID references missing/deleted amenity ids: {sorted(stale)}")
            return

        markets = (
            (
                await session.execute(
                    select(MarketKeysMaster).where(MarketKeysMaster.deleted_at.is_(None))
                )
            )
            .scalars()
            .all()
        )
        by_slug = {m.market_slug: m for m in markets}

        updated = 0
        skipped = 0
        for row in rows:
            market = by_slug.get(row["_slug"])
            if market is None:
                print(
                    f"  WARNING: slug '{row['_slug']}' not found in market_keys_master — skipping"
                )
                skipped += 1
                continue

            market.must_have_amenities = row["must_have_amenities"]
            market.nice_to_have_amenities = row["nice_to_have_amenities"]
            if row["analyst_owner"] is not None:
                market.analyst_owner = row["analyst_owner"]
            updated += 1

        if not updated:
            print(f"Nothing to update ({skipped} row(s) skipped).")
            return

        await session.commit()
        print(f"Updated {updated} market(s); {skipped} skipped.")


if __name__ == "__main__":
    asyncio.run(update())
