#!/usr/bin/env python3
"""Print the SQL that reseeds one underwriting's optimization (rehab) items.

The sibling of ``generate_uw_operating_expenses_sql.py``, for the other seeded
line-item table. Deals created before their market had amenity data — or before
the market was assigned — end up with an empty or partial
``iron_bank.uw_optimization_items``; this prints a DELETE + INSERT that replaces
it with the rows creation would have produced.

The list is built by ``BaseUnderwritingPayloadBuilder._build_optimization_list``
off a ``MarketContext`` from ``PrepareUwDataService.prepare_market_context`` —
the same two calls the automated and create-from-URL flows make — so the row
set, ordering, price tiers and ``sort_order`` stamping cannot drift from what
the app writes. The seeded options bracket the market's must-have amenities:
Furniture/Decor/Essentials first (priced at the MID tier), then the must-haves
in the market's own order (priced LOW, with the in-ground pool ids excluded),
then Design/Project Management and Install/Staging/Warehousing.

Note the inputs differ from the opex script: there is no purchase price (no
item is a function of it) and ``property_size`` is used RAW, not bucketed —
it selects the STR Cribs project-management fee tier, whose ``sqft`` column is
an inclusive upper bound rather than one of the opex checkpoints.

Prints SQL to stdout and writes nothing — read the output before committing.

Usage:
    uv run python scripts/generate_uw_optimization_items_sql.py \\
        --market-id 5 --bedrooms 4 --property-size 2080 --underwriting-id 516
"""

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.iron_bank.services.base_underwriting_payload_builder import (
    BaseUnderwritingPayloadBuilder,
)
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService
from app.markets.repositories.construction_repository import (
    ConstructionAmenitiesRepository,
)
from app.markets.repositories.market_repository import MarketRepository
from app.markets.repositories.opex_repository import OpexByBedroomsRepository
from app.markets.repositories.realtor_repository import RealtorRepository
from app.markets.repositories.str_cribs_repository import StrCribsFeeDetailsRepository
from app.markets.services.construction_service import ConstructionAmenitiesService
from app.markets.services.market_service import MarketService
from app.markets.services.opex_service import OpexByBedroomsService
from app.markets.services.str_cribs_service import StrCribsFeeDetailsService

UNDERWRITING_ID_PLACEHOLDER = ":underwriting_id"

# Columns _amenity_to_optimization_item fills, in insert order. ``spec`` and
# ``notes`` are deliberately absent: the seeded payload does not set them, so
# they must land NULL rather than be invented here.
COLUMNS = ("category", "total_price", "base_price", "metric", "tier")


def _sql_literal(value) -> str:
    if value is None:
        return "NULL"
    # format(..., "f") rather than str(): a Decimal carrying an exponent renders
    # as 6E+4, which Postgres accepts but nobody can proofread.
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


async def build_items(
    *,
    market_id: int | None,
    bedrooms: int,
    property_size: int,
    session_factory=AsyncSessionLocal,
) -> list[dict]:
    """The seeded optimization items for one market/bedrooms/size."""
    async with session_factory() as session:
        market_repo = MarketRepository(session)
        amenities_repo = ConstructionAmenitiesRepository(session)

        market_service = MarketService(
            market_repo, amenities_repo, RealtorRepository(session)
        )
        bedrooms_service = OpexByBedroomsService(
            OpexByBedroomsRepository(session), market_repo
        )
        amenities_service = ConstructionAmenitiesService(amenities_repo)
        str_cribs_service = StrCribsFeeDetailsService(
            StrCribsFeeDetailsRepository(session)
        )

        market = (
            await market_service.get_by_id(market_id) if market_id is not None else None
        )
        if market_id is not None and market is None:
            sys.exit(f"No active market with id={market_id}")

        opex_by_bedrooms = await bedrooms_service.get_by_market_and_bedrooms(
            bedrooms=bedrooms, market_id=market_id
        )
        construction_amenities = await amenities_service.get_all()
        # Raw area, not a bucketed sqft: the fee table's sqft is an inclusive
        # upper bound per tier (see StrCribsFeeDetailsRepository.get_by_area).
        str_cribs_fee = await str_cribs_service.get_by_area(property_size)

    if opex_by_bedrooms is None:
        print(
            f"-- WARNING: no markets.opex_by_bedrooms row for market_id={market_id}, "
            f"bedrooms={bedrooms}. Furniture/Decor/Essentials and "
            f"Install/Staging/Warehousing will be seeded with NULL prices.",
            file=sys.stderr,
        )
    if str_cribs_fee is None:
        print(
            f"-- WARNING: no markets str-cribs fee tier covers area={property_size}. "
            f"Design/Project Management will be seeded with a NULL price.",
            file=sys.stderr,
        )

    context = PrepareUwDataService().prepare_market_context(
        market=market,
        market_id=market_id,
        opex_by_bedrooms=opex_by_bedrooms,
        # Neither affects the amenity options; passed empty so this script can
        # reuse prepare_market_context rather than reimplement its amenity half.
        opex_by_size=None,
        construction_amenities=construction_amenities,
        construction_remodeling=[],
        fred=None,
        str_cribs_fee=str_cribs_fee,
    )
    return BaseUnderwritingPayloadBuilder()._build_optimization_list(
        context.model_dump()
    )


def render_sql(
    items: list[dict],
    *,
    underwriting_id: int | None,
    market_id: int | None,
    bedrooms: int,
    property_size: int,
) -> str:
    target = (
        str(underwriting_id)
        if underwriting_id is not None
        else UNDERWRITING_ID_PLACEHOLDER
    )

    lines = [
        f"-- underwriting_id={target}  market_id={market_id}  bedrooms={bedrooms}"
        f"  property_size={property_size}",
        f"-- {len(items)} optimization items"
        f"  (total {sum(i['total_price'] or 0 for i in items)})",
        "",
        "BEGIN;",
        "",
        "DELETE FROM iron_bank.uw_optimization_items",
        f"WHERE underwriting_id = {target};",
        "",
        "INSERT INTO iron_bank.uw_optimization_items",
        f"    (underwriting_id, {', '.join(COLUMNS)}, sort_order)",
        "VALUES",
    ]

    width = max((len(str(i["category"] or "")) for i in items), default=0) + 3
    values = []
    for index, item in enumerate(items):
        cells = [f"{_sql_literal(item['category']) + ',':<{width}}"]
        cells += [f"{_sql_literal(item[c]):>9}," for c in COLUMNS[1:3]]
        cells += [f"{_sql_literal(item[c]):>8}," for c in COLUMNS[3:]]
        # sort_order is the row's position in the emitted list, matching how
        # UnderwritingRepository stamps it from payload position on save.
        values.append(f"    ({target}, {' '.join(cells)} {index:2})")
    lines.append(",\n".join(values) + ";")

    lines += [
        "",
        "SELECT id, category, total_price, base_price, metric, tier, sort_order",
        "FROM iron_bank.uw_optimization_items",
        f"WHERE underwriting_id = {target}",
        "ORDER BY sort_order;",
        "",
        "-- Check the SELECT above before committing.",
        "COMMIT;",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print DELETE/INSERT SQL reseeding an underwriting's optimization items."
    )
    parser.add_argument("--market-id", type=int, required=True)
    parser.add_argument("--bedrooms", type=int, required=True)
    parser.add_argument(
        "--property-size",
        type=int,
        required=True,
        help="Living area in sqft, used raw to pick the STR Cribs fee tier",
    )
    parser.add_argument(
        "--underwriting-id",
        type=int,
        help=(
            "Deal to reseed. Omitted, the SQL is emitted with a "
            f"{UNDERWRITING_ID_PLACEHOLDER} placeholder instead."
        ),
    )
    args = parser.parse_args()

    items = asyncio.run(
        build_items(
            market_id=args.market_id,
            bedrooms=args.bedrooms,
            property_size=args.property_size,
        )
    )
    print(
        render_sql(
            items,
            underwriting_id=args.underwriting_id,
            market_id=args.market_id,
            bedrooms=args.bedrooms,
            property_size=args.property_size,
        )
    )


if __name__ == "__main__":
    main()
