"""Seed the shared reference-data options for the iron_bank deal tags.

Populates ``reference.enum_options`` (domain ``iron_bank``) with the slug/label
values for all 10 tag sets. Idempotent: an option is inserted only if its
(domain, set_code, key) triple doesn't already exist, so re-running is safe.

Slugs are what the underwriting tag columns store; labels live here only and can
be edited later via ``PATCH /reference-data/options/{id}``.

Usage:
    uv run python scripts/seeding_scripts/seed_enum_options.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.reference_data.models import EnumOption

DOMAIN = "iron_bank"

# set_code -> ordered list of (key, label). List order becomes sort_order.
# Multi-select sets (market_type, seasonality, core_value_driver) store a list
# of these slugs per underwriting; the rest store a single slug.
SETS: dict[str, list[tuple[str, str]]] = {
    "market_type": [
        ("lake", "Lake"),
        ("mountain", "Mountain"),
        ("urban", "Urban"),
        ("hybrid", "Hybrid"),
        ("beach", "Beach"),
        ("coastal", "Coastal"),
        ("driveable", "Driveable"),
        ("national_park", "National Park"),
        ("henry", "HENRY"),
        ("remote", "Remote"),
    ],
    "execution_type": [
        ("light", "Light"),
        ("moderate", "Moderate"),
        ("heavy", "Heavy"),
    ],
    "seasonality": [
        ("jan", "Jan"),
        ("feb", "Feb"),
        ("mar", "Mar"),
        ("apr", "Apr"),
        ("may", "May"),
        ("jun", "June"),
        ("jul", "July"),
        ("aug", "Aug"),
        ("sep", "Sept"),
        ("oct", "Oct"),
        ("nov", "Nov"),
        ("dec", "Dec"),
    ],
    "regulatory_clarity": [
        ("light", "Light"),
        ("moderate", "Moderate"),
        ("heavy", "Heavy"),
    ],
    "offer_competitiveness": [
        ("low", "Low"),
        ("moderate", "Moderate"),
        ("high", "High"),
    ],
    "core_value_driver": [
        ("views", "Views"),
        ("seclusion", "Seclusion"),
        ("location", "Location"),
        ("amenities", "Amenities"),
        ("size", "Size"),
        ("uniqueness", "Uniqueness"),
        ("luxury", "Luxury"),
        ("lot_size", "Lot Size"),
    ],
    # Single-select but backend-derived from Low CoC% (Low <=5, Mid 5-8, High >8).
    # Thresholds are stashed in metadata so the future compute step reads them
    # from one place instead of hard-coding.
    "cash_flow_quality": [
        ("low", "Low"),
        ("mid", "Mid"),
        ("high", "High"),
    ],
    "view_quality": [
        ("none", "None"),
        ("partial", "Partial"),
        ("premium", "Premium"),
    ],
    "pool_type": [
        ("none", "None"),
        ("above_ground", "Above Ground"),
        ("in_ground", "In-ground"),
        ("public_pool", "Public Pool"),
    ],
    "primary_guest_avatar": [
        ("group_trips", "Group Trips"),
        ("family_stays", "Family Stays"),
        ("couples_getaway", "Couples Getaway"),
    ],
}

# Optional per-option metadata, keyed by (set_code, key). Documents the
# Low CoC% thresholds that drive the derived cash_flow_quality value.
METADATA: dict[tuple[str, str], dict] = {
    ("cash_flow_quality", "low"): {"low_coc_pct_max": 5},
    ("cash_flow_quality", "mid"): {"low_coc_pct_min": 5, "low_coc_pct_max": 8},
    ("cash_flow_quality", "high"): {"low_coc_pct_min": 8},
}


async def seed(session_factory=AsyncSessionLocal) -> None:
    async with session_factory() as session:
        existing = (
            (
                await session.execute(
                    select(EnumOption.set_code, EnumOption.key).where(
                        EnumOption.domain == DOMAIN
                    )
                )
            )
            .all()
        )
        existing_keys = {(row.set_code, row.key) for row in existing}

        to_insert: list[EnumOption] = []
        for set_code, options in SETS.items():
            for sort_order, (key, label) in enumerate(options):
                if (set_code, key) in existing_keys:
                    continue
                to_insert.append(
                    EnumOption(
                        domain=DOMAIN,
                        set_code=set_code,
                        key=key,
                        label=label,
                        sort_order=sort_order,
                        is_active=True,
                        is_default=False,
                        metadata_json=METADATA.get((set_code, key)),
                    )
                )

        if to_insert:
            session.add_all(to_insert)
            await session.commit()

    total = sum(len(v) for v in SETS.values())
    print(
        f"Seeded {len(to_insert)} new option(s); "
        f"{total - len(to_insert)} already present "
        f"({total} total across {len(SETS)} sets, domain='{DOMAIN}')."
    )


if __name__ == "__main__":
    asyncio.run(seed())
