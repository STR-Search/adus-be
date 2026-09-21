#!/usr/bin/env python3
"""Print the SQL that reseeds one underwriting's operating expenses.

For deals that were saved before their market had opex data — an exploratory
market, typically — ``uw_operating_expenses`` holds only the always-seeded rows
(Property Taxes, MISC) at zero. Once the market's ``opex_by_bedrooms`` and
``opex_by_size`` rows exist, this prints a DELETE + INSERT that replaces the
placeholders with the rows creation would have produced.

The figures come from ``opex_catalog``, the same module the seeding and read
paths use, so the row set, the labels, the derived amounts (cleaning, pool/hot
tub, property taxes) and the ``sort_order`` stamping cannot drift from what the
app writes. ``property_size`` is bucketed through
``PrepareUwDataService.normalize_sqft`` exactly as the prepare step does, so the
``opex_by_size`` row picked here is the one the deal would have been seeded
from.

Prints SQL to stdout and writes nothing — pipe it to psql or paste it into a
session, and read the output before committing.

Usage:
    uv run python scripts/generate_uw_operating_expenses_sql.py \\
        --market-id 108 --bedrooms 3 --property-size 2425 \\
        --purchase-price 850000 --underwriting-id 2519
"""

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.iron_bank.services import opex_catalog
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService
from app.markets.repositories.market_repository import MarketRepository
from app.markets.repositories.opex_repository import (
    OpexByBedroomsRepository,
    OpexBySizeRepository,
)
from app.markets.services.opex_service import OpexByBedroomsService, OpexBySizeService

# Stands in for the id when none is given, so the output is still a usable
# template — psql expands it as a variable, other clients need it substituted.
UNDERWRITING_ID_PLACEHOLDER = ":underwriting_id"


def _sql_literal(value) -> str:
    """Render a Python value as a SQL literal.

    Only the amounts reach this; labels come from ``OPEX_ROWS`` and are fixed
    strings, but they are escaped anyway rather than trusting that to stay true.
    """
    if value is None:
        return "NULL"
    if isinstance(value, (int, Decimal)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


async def build_rows(
    *,
    market_id: int,
    bedrooms: int,
    property_size: int,
    purchase_price: Decimal,
    session_factory=AsyncSessionLocal,
) -> tuple[list[dict], int]:
    """The seeded expense rows for one market/bedrooms/size/price, plus the sqft bucket."""
    sqft = PrepareUwDataService().normalize_sqft(property_size)

    async with session_factory() as session:
        market_repo = MarketRepository(session)
        bedrooms_service = OpexByBedroomsService(
            OpexByBedroomsRepository(session), market_repo
        )
        size_service = OpexBySizeService(OpexBySizeRepository(session), market_repo)

        opex_by_bedrooms = await bedrooms_service.get_by_market_and_bedrooms(
            bedrooms=bedrooms, market_id=market_id
        )
        opex_by_size = await size_service.get_by_market_and_sqft(
            sqft=sqft, market_id=market_id
        )

    if opex_by_bedrooms is None:
        print(
            f"-- WARNING: no markets.opex_by_bedrooms row for "
            f"market_id={market_id}, bedrooms={bedrooms}. Every bedrooms-keyed "
            f"row will be dropped.",
            file=sys.stderr,
        )
    if opex_by_size is None:
        print(
            f"-- WARNING: no markets.opex_by_size row for market_id={market_id}, "
            f"sqft={sqft} (bucketed from property_size={property_size}). "
            f"Internet, Utilities and Pest Control will be dropped.",
            file=sys.stderr,
        )

    opex = opex_catalog.transform_opex_costs(opex_by_bedrooms, opex_by_size)
    property_taxes = opex_catalog.build_opex_property_taxes(
        property_tax_pct=opex.get("property_tax_pct"),
        purchase_price=purchase_price,
    )
    return opex_catalog.build_opex_expense_rows(opex, property_taxes), sqft


def render_sql(
    rows: list[dict],
    *,
    underwriting_id: int | None,
    market_id: int,
    bedrooms: int,
    property_size: int,
    sqft: int,
    purchase_price: Decimal,
) -> str:
    target = (
        str(underwriting_id)
        if underwriting_id is not None
        else UNDERWRITING_ID_PLACEHOLDER
    )

    lines = [
        f"-- underwriting_id={target}  market_id={market_id}  bedrooms={bedrooms}",
        (
            f"-- property_size={property_size} -> opex_by_size.sqft={sqft}"
            f"  purchase_price={purchase_price}"
        ),
        f"-- {len(rows)} of {len(opex_catalog.OPEX_ROWS)} catalog rows resolved",
        "",
        "BEGIN;",
        "",
        "DELETE FROM iron_bank.uw_operating_expenses",
        f"WHERE underwriting_id = {target};",
        "",
        "INSERT INTO iron_bank.uw_operating_expenses",
        "    (underwriting_id, expense_name, monthly_amount, sort_order)",
        "VALUES",
    ]

    # Longest label plus its two quotes and trailing comma, so the amount
    # column lines up even on the widest row.
    width = max((len(row["expense"]) for row in rows), default=0) + 3
    values = [
        f"    ({target}, {_sql_literal(row['expense']) + ',':<{width}} "
        f"{_sql_literal(row['monthly']):>10}, {index:2})"
        # sort_order is the row's position in the emitted list, matching how
        # UnderwritingRepository stamps it from payload position on save.
        for index, row in enumerate(rows)
    ]
    lines.append(",\n".join(values) + ";")

    lines += [
        "",
        "SELECT id, expense_name, monthly_amount, sort_order",
        "FROM iron_bank.uw_operating_expenses",
        f"WHERE underwriting_id = {target}",
        "ORDER BY sort_order;",
        "",
        "-- Check the SELECT above before committing.",
        "COMMIT;",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print DELETE/INSERT SQL reseeding an underwriting's operating expenses."
    )
    parser.add_argument("--market-id", type=int, required=True)
    parser.add_argument("--bedrooms", type=int, required=True)
    parser.add_argument(
        "--property-size",
        type=int,
        required=True,
        help="Living area in sqft; bucketed to an opex_by_size checkpoint",
    )
    parser.add_argument("--purchase-price", type=Decimal, required=True)
    parser.add_argument(
        "--underwriting-id",
        type=int,
        help=(
            "Deal to reseed. Omitted, the SQL is emitted with a "
            f"{UNDERWRITING_ID_PLACEHOLDER} placeholder instead."
        ),
    )
    args = parser.parse_args()

    rows, sqft = asyncio.run(
        build_rows(
            market_id=args.market_id,
            bedrooms=args.bedrooms,
            property_size=args.property_size,
            purchase_price=args.purchase_price,
        )
    )
    print(
        render_sql(
            rows,
            underwriting_id=args.underwriting_id,
            market_id=args.market_id,
            bedrooms=args.bedrooms,
            property_size=args.property_size,
            sqft=sqft,
            purchase_price=args.purchase_price,
        )
    )


if __name__ == "__main__":
    main()
