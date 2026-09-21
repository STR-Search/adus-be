"""Seed optimization_expense_lift / low_revenue_lift on the active markets.

Values below are the percentages the analysts supplied; they are stored as
multipliers, so 25% becomes 1.25 and 0% becomes 1.00. (A down-lift would be a
negative percentage, e.g. -10% -> 0.90; the current set has none.)

Usage:
    uv run python scripts/seeding_scripts/seed_market_lifts.py [--dry-run]
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.markets.models import MarketKeysMaster

# market_slug -> (optimization_expense_lift %, low_revenue_lift %)
LIFT_PERCENTAGES: dict[str, tuple[str, str]] = {
    "albrightsville-pa": ("0.00", "7.00"),
    "albuquerque-nm": ("0.00", "3.00"),
    "asheville-nc": ("0.00", "5.00"),
    "austin-tx-no-lake": ("0.00", "5.00"),
    "blue-ridge-ga": ("0.00", "3.00"),
    "bradenton-fl": ("0.00", "7.00"),
    "broken-bow-ok": ("0.00", "5.00"),
    "charlotte-nc": ("0.00", "3.00"),
    "clearwater-fl-greater-area": ("0.00", "7.00"),
    "columbus-oh": ("0.00", "3.00"),
    "cripple-creek-co": ("0.00", "0.00"),
    "denver-co-greater-area": ("0.00", "5.00"),
    "east-stroudsburg-pa": ("0.00", "7.00"),
    "ellijay-ga": ("0.00", "0.00"),
    "finger-lakes-ny": ("25.00", "3.00"),
    "fort-lauderdale-fl": ("0.00", "3.00"),
    "galena-il": ("0.00", "5.00"),
    "gatlinburg-tn": ("0.00", "5.00"),
    "greene-county-ny": ("25.00", "5.00"),
    "hot-springs-ar": ("0.00", "0.00"),
    "indianapolis-in": ("0.00", "3.00"),
    "lake-harmony-pa": ("0.00", "7.00"),
    "lower-hudson-valley-ny": ("25.00", "3.00"),
    "massanuten-va": ("0.00", "7.00"),
    "miami-fl": ("0.00", "3.00"),
    "north-scottsdale-az": ("0.00", "7.00"),
    "pagosa-springs-co": ("0.00", "0.00"),
    "panama-city-beach-fl": ("0.00", "5.00"),
    "penn-estates-pa": ("0.00", "7.00"),
    "pigeon-forge-tn": ("0.00", "5.00"),
    "poconos-pines-pa": ("0.00", "7.00"),
    "rockbridge-oh": ("0.00", "0.00"),
    "san-antonio-tx": ("0.00", "3.00"),
    "sedona-az": ("0.00", "3.00"),
    "sevierville-tn": ("0.00", "5.00"),
    "shenandoah-valley-va": ("0.00", "5.00"),
    "saint-augustine-fl": ("0.00", "5.00"),
    "tampa-fl": ("0.00", "7.00"),
    "texas-hill-country-tx": ("0.00", "5.00"),
    "tobyhanna-pa": ("0.00", "7.00"),
    "tucson-az": ("0.00", "0.00"),
    "upper-hudson-valley-ny": ("25.00", "3.00"),
    "west-palm-beach-fl": ("0.00", "5.00"),
    "western-hudson-valley-ny": ("25.00", "3.00"),
    "wintergreen-va": ("0.00", "0.00"),
    "milwaukee-wi": ("0.00", "3.00"),
    "bailey-co": ("0.00", "3.00"),
    "alma-fairplay-co": ("0.00", "3.00"),
}


def to_multiplier(percentage: str) -> Decimal:
    """7.00 (%) -> 1.07, kept at the scale the column stores."""
    return (Decimal(1) + Decimal(percentage) / Decimal(100)).quantize(Decimal("0.0001"))


async def seed(dry_run: bool = False) -> None:
    async with AsyncSessionLocal() as session:
        markets = (
            (
                await session.execute(
                    select(MarketKeysMaster).where(
                        MarketKeysMaster.market_slug.in_(LIFT_PERCENTAGES),
                        MarketKeysMaster.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )

        by_slug = {market.market_slug: market for market in markets}
        missing = sorted(LIFT_PERCENTAGES.keys() - by_slug.keys())

        updated = 0
        for slug, (expense_pct, revenue_pct) in LIFT_PERCENTAGES.items():
            market = by_slug.get(slug)
            if market is None:
                continue
            expense_lift = to_multiplier(expense_pct)
            revenue_lift = to_multiplier(revenue_pct)
            print(f"  {slug}: {expense_lift} / {revenue_lift}")
            market.optimization_expense_lift = expense_lift
            market.low_revenue_lift = revenue_lift
            updated += 1

        if missing:
            print(f"Skipped {len(missing)} slug(s) not found among active markets:")
            for slug in missing:
                print(f"  {slug}")

        if dry_run:
            await session.rollback()
            print(f"Dry run — would set lifts on {updated} market(s).")
            return

        await session.commit()
        print(f"Set lifts on {updated} market(s).")


if __name__ == "__main__":
    asyncio.run(seed(dry_run="--dry-run" in sys.argv))
