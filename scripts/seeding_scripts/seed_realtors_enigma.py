"""Temporary script: seed markets.realtors from 'Enigma-Master - markets.csv'
and point each market's realtor_ids at the seeded rows.

The CSV carries one Realtor_Name / Realtor_Email pair per market, but the same
realtor covers several markets (Xander W appears in 6). Realtors are therefore
deduplicated on the normalized email — lowercased and stripped, matching the
uq_realtors_email_active index — so each person gets exactly one row that every
market they cover references by id.

Source data is dirty: leading tabs on names, trailing spaces, inconsistent
email casing. All of it is normalized here rather than in the API schemas.

Rows with a name but no email cannot be deduplicated reliably and are skipped
with a warning. Empty cells set realtor_ids to NULL. Slugs missing from the DB
are skipped (this script updates markets — it does not insert them).

Re-running is safe: existing realtors are matched by email and updated in
place rather than duplicated.
"""

import asyncio
import csv
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.markets.models import MarketKeysMaster
from app.markets.models.realtor import Realtor

CSV_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "scratch_pad"
    / "Enigma-Master - markets.csv"
)


def _clean(value: str | None) -> str | None:
    """Strip surrounding whitespace (including the stray tabs in the source)
    and collapse blank cells to None."""
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def load_rows() -> list[dict]:
    rows = []
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            slug = _clean(row["market_slug"])
            if not slug:
                continue
            name = _clean(row.get("Realtor_Name"))
            email = _clean(row.get("Realtor_Email"))
            if name and not email:
                print(
                    f"  WARNING: realtor '{name}' (slug '{slug}') has no email — "
                    "cannot deduplicate, skipping"
                )
                name = None
            rows.append(
                {
                    "_slug": slug,
                    "name": name,
                    "email": _normalize_email(email) if email else None,
                }
            )
    return rows


async def seed():
    rows = load_rows()
    if not rows:
        print("No rows loaded from CSV.")
        return

    # Deduplicate on normalized email; last non-null name for an email wins.
    by_email: dict[str, str | None] = {}
    for row in rows:
        if row["email"] is None:
            continue
        by_email.setdefault(row["email"], row["name"])

    if not by_email:
        print("No realtors found in CSV.")
        return

    async with AsyncSessionLocal() as session:
        existing = (
            (
                await session.execute(
                    select(Realtor).where(Realtor.deleted_at.is_(None))
                )
            )
            .scalars()
            .all()
        )
        realtor_by_email = {
            _normalize_email(r.email): r for r in existing if r.email
        }

        created = 0
        for email, name in by_email.items():
            realtor = realtor_by_email.get(email)
            if realtor is None:
                realtor = Realtor(name=name, email=email)
                session.add(realtor)
                realtor_by_email[email] = realtor
                created += 1
            elif name and realtor.name != name:
                realtor.name = name

        # Flush so newly-added realtors get ids before markets reference them.
        await session.flush()

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
                    f"  WARNING: slug '{row['_slug']}' not found in "
                    "market_keys_master — skipping"
                )
                skipped += 1
                continue

            if row["email"] is None:
                market.realtor_ids = None
            else:
                market.realtor_ids = [realtor_by_email[row["email"]].id]
            updated += 1

        await session.commit()
        print(
            f"Seeded {created} new realtor(s) ({len(by_email)} unique in CSV); "
            f"updated {updated} market(s); {skipped} skipped."
        )


if __name__ == "__main__":
    asyncio.run(seed())
