"""One-time migration: reassign `iron_bank.underwritings` analyst_id/
approver_id rows off the disposable `legacy_xxx` placeholder users created
by backfill_legacy_underwritings.py before it mapped sheet labels to real
accounts, onto the real users those labels always meant.

Run once, by hand, after that mapping fix has landed and been verified.

Scope: the 7 placeholders below (confirmed via users.users). `legacy_aleric`
(id 35) is deliberately excluded -- no real account exists for that person,
so it's left untouched entirely, not reassigned or deleted.

    legacy id -> real id
    32 (Mark)     -> 41 (Mark Harold Isidro)
    33 (Kevin)    -> 45 (Kevin Kyle Barce Santos)
    34 (Chris K)  -> 50 (Chris Klingemann)
    36 (David C)  -> 59 (David Cummings)
    37 (Van)      -> 43 (Van Hussen Manuel)
    38 (Chris)    -> 50 (Chris Klingemann)
    39 (Aldwin)   -> 49 (Aldwin Dabuet Albite)

For each legacy id, this:
  1. Pre-flight checks every FK to users.users.id for unexpected references
     -- owner_id, markets.market_keys_master.analyst_owner_id,
     users.saved_searches.user_id, users.api_keys.user_id -- all expected
     zero. saved_searches is ON DELETE CASCADE and api_keys has no ondelete
     (defaults RESTRICT), so a nonzero count there means something this
     script wasn't told about depends on this id; it aborts rather than
     guessing.
  2. Reassigns analyst_id/approver_id from legacy id to real id.
  3. Soft-deletes the legacy user (is_deleted = true) -- not a hard DELETE,
     since that's all that's needed to drop it from
     build_user_matcher()'s candidate pool, with no FK risk to reason about.

Usage:
  python scripts/reassign_legacy_placeholder_users.py --dry-run
  python scripts/reassign_legacy_placeholder_users.py
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

LEGACY_TO_REAL: dict[int, int] = {
    32: 41,  # Mark -> Mark Harold Isidro
    33: 45,  # Kevin -> Kevin Kyle Barce Santos
    34: 50,  # Chris K -> Chris Klingemann
    36: 59,  # David C -> David Cummings
    37: 43,  # Van -> Van Hussen Manuel
    38: 50,  # Chris -> Chris Klingemann
    39: 49,  # Aldwin -> Aldwin Dabuet Albite
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reassign underwritings off legacy_xxx placeholder users onto "
            "the real users they stood in for, then soft-delete the "
            "placeholders."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pre-flight checks and report planned changes; no writes.",
    )
    return parser.parse_args()


async def run(dry_run: bool) -> None:
    from sqlalchemy import text

    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        for legacy_id, real_id in LEGACY_TO_REAL.items():
            owner_count = (
                await session.execute(
                    text(
                        "select count(*) from iron_bank.underwritings "
                        "where owner_id = :id"
                    ),
                    {"id": legacy_id},
                )
            ).scalar_one()
            market_count = (
                await session.execute(
                    text(
                        "select count(*) from markets.market_keys_master "
                        "where analyst_owner_id = :id"
                    ),
                    {"id": legacy_id},
                )
            ).scalar_one()
            saved_search_count = (
                await session.execute(
                    text(
                        "select count(*) from users.saved_searches "
                        "where user_id = :id"
                    ),
                    {"id": legacy_id},
                )
            ).scalar_one()
            api_key_count = (
                await session.execute(
                    text("select count(*) from users.api_keys where user_id = :id"),
                    {"id": legacy_id},
                )
            ).scalar_one()

            if owner_count or market_count or saved_search_count or api_key_count:
                sys.exit(
                    f"legacy user {legacy_id}: unexpected references found "
                    f"(owner_id={owner_count}, analyst_owner_id={market_count}, "
                    f"saved_searches={saved_search_count}, api_keys={api_key_count}) "
                    "-- aborting, nothing was written. Resolve manually."
                )

        summary: dict[int, dict[str, int]] = {}
        for legacy_id, real_id in LEGACY_TO_REAL.items():
            analyst_result = await session.execute(
                text(
                    "update iron_bank.underwritings set analyst_id = :real "
                    "where analyst_id = :legacy"
                ),
                {"real": real_id, "legacy": legacy_id},
            )
            approver_result = await session.execute(
                text(
                    "update iron_bank.underwritings set approver_id = :real "
                    "where approver_id = :legacy"
                ),
                {"real": real_id, "legacy": legacy_id},
            )
            summary[legacy_id] = {
                "real_id": real_id,
                "analyst_rows": analyst_result.rowcount,
                "approver_rows": approver_result.rowcount,
            }

        await session.execute(
            text("update users.users set is_deleted = true where id = any(:ids)"),
            {"ids": list(LEGACY_TO_REAL.keys())},
        )

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    print(f"{'[DRY RUN] ' if dry_run else ''}Reassignment summary:")
    for legacy_id, info in summary.items():
        print(
            f"  legacy id {legacy_id} -> real id {info['real_id']}: "
            f"{info['analyst_rows']} analyst_id rows, "
            f"{info['approver_rows']} approver_id rows"
        )
    print(
        f"{'Would soft-delete' if dry_run else 'Soft-deleted'} "
        f"{len(LEGACY_TO_REAL)} placeholder users: "
        f"{sorted(LEGACY_TO_REAL.keys())}"
    )
    print("legacy_aleric (id 35) was not touched.")


def main() -> None:
    args = parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
