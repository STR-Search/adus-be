"""Seed the deal_status process log with each existing underwriting's status.

The process log only records changes from the day it shipped. This gives every
underwriting that has a ``deal_status`` but no history yet one head row:
``NULL → <current status>``, ``source='backfill'``, with a full snapshot of the
deal as it is now. It says "was in this status as of this time", not "entered
it then". Design: ``docs/features/process_log/process_log.md`` §5.

``occurred_at`` is ``deal_approved`` for present_to_clients / client_under_contract
when set, else ``updated_at``, else ``created_at``. The actor is the approver for
those two statuses and NULL otherwise. Deals with a NULL status are skipped; their
first status change starts their history.

Idempotent: deals that already have a head row (from the live write path or an
earlier run) are skipped, so a rerun inserts nothing. Run it after the write path
is deployed, so no deal changes status without being logged in between.

Ends with the drift check: every deal's latest logged status must equal its
current ``deal_status``.

Usage:
  uv run python scripts/backfill_deal_status_history.py --dry-run
  uv run python scripts/backfill_deal_status_history.py
  uv run python scripts/backfill_deal_status_history.py --check-only
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import exists, func, select, text
from sqlalchemy.orm import selectinload

from app.core.process_log.enums import Flow, SubjectType, TransitionSource
from app.core.process_log.models import Transition
from app.core.process_log.repository import ProcessLogRepository
from app.core.process_log.schemas import HeadSeed
from app.core.process_log.service import ProcessLogService
from app.iron_bank.enums import DealStatus
from app.iron_bank.models import Underwriting
from app.iron_bank.services.deal_status_history import (
    build_underwriting_snapshot,
)

SEED_NOTE = "seeded from current status"
_APPROVED_STATUSES = frozenset(
    {DealStatus.PRESENT_TO_CLIENTS.value, DealStatus.CLIENT_UNDER_CONTRACT.value}
)

DEV_PROJECT_REF = "czixmnswofswzcuhgnwa"
PROD_PROJECT_REF = "cnunaeslrrgetewuxsty"

# Deals whose latest logged status differs from their current status. Run
# after seeding; should return no rows.
DRIFT_SQL = """
SELECT u.id, u.deal_status, t.to_status AS logged_status
FROM iron_bank.underwritings u
LEFT JOIN process_log.transitions t
  ON t.subject_type = 'underwriting' AND t.subject_id = u.id
 AND t.flow = 'deal_status'
 AND NOT EXISTS (
     SELECT 1 FROM process_log.transitions n WHERE n.previous_transition_id = t.id
 )
WHERE u.deal_status IS DISTINCT FROM t.to_status
ORDER BY u.id
"""


def _has_head():
    return exists().where(
        Transition.subject_type == SubjectType.UNDERWRITING.value,
        Transition.subject_id == Underwriting.id,
        Transition.flow == Flow.DEAL_STATUS.value,
        Transition.previous_transition_id.is_(None),
    )


def head_seed_for(underwriting: Underwriting) -> HeadSeed:
    """The head row for one underwriting's current status."""
    status = underwriting.deal_status
    approved = status in _APPROVED_STATUSES
    occurred_at = (
        (underwriting.deal_approved if approved else None)
        or underwriting.updated_at
        or underwriting.created_at
    )
    return HeadSeed(
        subject_type=SubjectType.UNDERWRITING.value,
        subject_id=underwriting.id,
        flow=Flow.DEAL_STATUS.value,
        to_status=status,
        source=TransitionSource.BACKFILL.value,
        actor_user_id=underwriting.approver_id if approved else None,
        note=SEED_NOTE,
        occurred_at=occurred_at,
        snapshot=build_underwriting_snapshot(underwriting),
    )


async def report(session) -> dict[str, Any]:
    by_status = (
        await session.execute(
            select(Underwriting.deal_status, func.count())
            .where(Underwriting.deal_status.is_not(None), ~_has_head())
            .group_by(Underwriting.deal_status)
            .order_by(func.count().desc())
        )
    ).all()
    null_status = await session.scalar(
        select(func.count()).where(Underwriting.deal_status.is_(None))
    )
    already = await session.scalar(
        select(func.count()).where(Underwriting.deal_status.is_not(None), _has_head())
    )
    return {
        "to_seed": sum(count for _, count in by_status),
        "to_seed_by_status": {status: count for status, count in by_status},
        "already_have_history": already,
        "skipped_null_status": null_status,
    }


async def seed(session, *, batch_size: int) -> int:
    service = ProcessLogService(ProcessLogRepository(session))
    inserted = 0
    last_id = 0
    while True:
        batch = (
            (
                await session.execute(
                    select(Underwriting)
                    .where(
                        Underwriting.id > last_id,
                        Underwriting.deal_status.is_not(None),
                        ~_has_head(),
                    )
                    .order_by(Underwriting.id)
                    .limit(batch_size)
                    .options(
                        selectinload(Underwriting.detail),
                        selectinload(Underwriting.taxes),
                        selectinload(Underwriting.optimization_items),
                        selectinload(Underwriting.operating_expenses),
                        selectinload(Underwriting.comp_set),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not batch:
            return inserted
        inserted += await service.seed_heads([head_seed_for(u) for u in batch])
        await session.commit()
        last_id = batch[-1].id
        # Committed rows are no longer needed; keep memory flat across batches.
        session.expunge_all()
        print(f"  seeded through underwriting {last_id}: {inserted} so far")


async def drift(session) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in (await session.execute(text(DRIFT_SQL)))]


def target_label(url: str) -> str:
    if PROD_PROJECT_REF in url:
        return "PROD"
    if DEV_PROJECT_REF in url:
        return "DEV"
    return "UNKNOWN"


async def run(*, dry_run: bool, check_only: bool, batch_size: int) -> dict[str, Any]:
    from app.core.config import get_config
    from app.core.database import AsyncSessionLocal

    result: dict[str, Any] = {
        "target": target_label(get_config().async_database_url),
        "dry_run": dry_run,
    }
    async with AsyncSessionLocal() as session:
        if not check_only:
            result["before"] = await report(session)
            if not dry_run:
                result["inserted"] = await seed(session, batch_size=batch_size)
                result["after"] = await report(session)
        mismatches = await drift(session)
    result["drift_count"] = len(mismatches)
    result["drift_sample"] = mismatches[:10]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="Report counts; write nothing"
    )
    parser.add_argument(
        "--check-only", action="store_true", help="Only run the drift check"
    )
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    result = asyncio.run(
        run(
            dry_run=args.dry_run,
            check_only=args.check_only,
            batch_size=args.batch_size,
        )
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
