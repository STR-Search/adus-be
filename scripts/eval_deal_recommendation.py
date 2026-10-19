#!/usr/bin/env python3
"""Run the deal-recommendation agent on real past client calls and score it.

Each case is a Fathom summary plus the deals the acquisition team actually sent
afterwards (scripts/fixtures/deal_recommendation_eval_cases.json). The agent
runs against the pool as it was in the weeks after the call — present_to_clients
and client_under_contract deals approved in the case's window — and is scored
on how many of its picks the team also sent, against random guessing.

Every case is a real agent run and costs real API money.

Usage:
    uv run python scripts/eval_deal_recommendation.py [--case NAME] [--yes]
"""

import argparse
import asyncio
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.deal_recommendation.agent.context import PoolOverride  # noqa: E402
from app.deal_recommendation.repositories.conversation_repository import (  # noqa: E402
    ConversationRepository,
)
from app.deal_recommendation.repositories.recommendation_repository import (  # noqa: E402
    RecommendationRepository,
)
from app.deal_recommendation.repositories.run_repository import RunRepository  # noqa: E402
from app.deal_recommendation.services.eval_scoring import score_case  # noqa: E402
from app.deal_recommendation.services.pool import dedupe_by_address  # noqa: E402
from app.deal_recommendation.services.run_manager import RunManager  # noqa: E402
from app.iron_bank.services.deal_catalog_service import DealCatalogService  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "deal_recommendation_eval_cases.json"
EVAL_STATUSES = ["present_to_clients", "client_under_contract"]
ESTIMATED_USD_PER_CASE = 2
SEARCH_TOOLS = {"search_deals", "find_similar_deals"}


async def run_case(case: dict, manager: RunManager) -> dict:
    window = case["pool_window"]
    override = PoolOverride(
        statuses=EVAL_STATUSES,
        approved_from=date.fromisoformat(window["approved_from"]),
        approved_to=date.fromisoformat(window["approved_to"]),
        property_pending=None,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    async with AsyncSessionLocal() as session:
        conversation = await ConversationRepository(session).create(
            title=f"eval:{case['name']}:{stamp}", created_by_user_id=None, model="eval"
        )
        await session.commit()
        conversation_id = conversation.id

    result = await manager.run_to_completion(
        conversation_id=conversation_id,
        text=case["summary"],
        user_id=None,
        pool_override=override,
    )

    async with AsyncSessionLocal() as session:
        runs = RunRepository(session)
        [run] = await runs.list_runs(conversation_id)
        _, calls = await runs.get_trace(run.id)
        recs = [
            r
            for r in await RecommendationRepository(session).list_for_conversation(conversation_id)
            if r.run_id == run.id
        ]
        searches = [c for c in calls if c.tool_name in SEARCH_TOOLS and not c.is_error]
        last_search_ids = (
            [c["id"] for c in searches[-1].output.get("candidates", [])] if searches else []
        )
        down = (await RecommendationRepository(session).latest_profile(conversation_id) or {}).get(
            "financing", {}
        ).get("down_payment_pct")
        pool = await DealCatalogService.for_session(session).list_candidate_pool(
            statuses=override.statuses,
            property_pending=None,
            approved_from=override.approved_from,
            approved_to=override.approved_to,
            down_payment_pct=None if down is None else Decimal(str(down)),
        )
    score = score_case(
        case_name=case["name"],
        sent_addresses=case["sent_addresses"],
        pool=dedupe_by_address(pool.deals),
        shortlist_ids=[r.underwriting_id for r in sorted(recs, key=lambda r: r.rank)],
        last_search_ids=last_search_ids,
    )
    return {
        "score": score,
        "status": result.status,
        "cost_usd": run.cost_usd,
        "run_id": run.id,
        "conversation_id": conversation_id,
    }


def print_table(rows: list[dict]) -> None:
    header = (
        f"{'case':<14}{'status':<11}{'pool':>6}{'sent':>6}"
        f"{'short hits':>12}{'random':>8}{'top20 hits':>12}{'random':>8}{'cost':>9}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        s = row["score"]
        print(
            f"{s.case:<14}{row['status']:<11}{s.pool_size:>6}{s.sent_in_pool:>6}"
            f"{f'{s.shortlist_hits}/{s.shortlist_size}':>12}{s.random_shortlist:>8}"
            f"{s.top20_hits:>12}{s.random_top20:>8}{'$' + str(row['cost_usd']):>9}"
        )
    for row in rows:
        print(f"{row['score'].case}: run {row['run_id']} · conversation {row['conversation_id']}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", help="Run one case by name")
    parser.add_argument("--yes", action="store_true", help="Skip the cost confirmation")
    args = parser.parse_args()

    cases = json.loads(FIXTURE.read_text())["cases"]
    if args.case:
        cases = [c for c in cases if c["name"] == args.case]
        if not cases:
            sys.exit(f"No case named {args.case!r}")
    if not args.yes:
        answer = input(
            f"This runs {len(cases)} real agent run(s) "
            f"(~${ESTIMATED_USD_PER_CASE * len(cases)} estimated) — continue? [y/N] "
        )
        if answer.strip().lower() != "y":
            sys.exit("Aborted")

    manager = RunManager()
    rows = []
    for case in cases:
        print(f"Running {case['name']}…", flush=True)
        rows.append(await run_case(case, manager))
    print()
    print_table(rows)


if __name__ == "__main__":
    asyncio.run(main())
