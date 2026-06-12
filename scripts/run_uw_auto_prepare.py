import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.workflows.batch_prepare_and_save_underwritings_job import (
    BatchPrepareAndSaveUnderwritingsJob,
)
from app.workflows.prepare_and_save_underwriting_job import PrepareAndSaveUnderwritingJob


async def run_batch(
    *,
    since_hours: int,
    limit: int | None,
    session_factory=AsyncSessionLocal,
    job_cls=BatchPrepareAndSaveUnderwritingsJob,
) -> dict[str, Any]:
    async with session_factory() as session:
        job = job_cls.from_session(session)
        return await job.run(since_hours=since_hours, limit=limit)


async def run_single(
    *,
    zpid: str,
    session_factory=AsyncSessionLocal,
    job_cls=PrepareAndSaveUnderwritingJob,
) -> dict[str, Any]:
    async with session_factory() as session:
        job = job_cls.from_session(session)
        return await job.run(zpid)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare and save draft underwriting rows for recent Zillow listings."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--since-hours", type=int, help="Process listings from the last N hours.")
    group.add_argument("--zpid", type=str, help="Process a single listing by zpid.")
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.zpid is not None:
        summary = asyncio.run(run_single(zpid=args.zpid))
    else:
        summary = asyncio.run(
            run_batch(
                since_hours=args.since_hours,
                limit=args.limit,
            )
        )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
