"""The canonical operating-expense catalog: one definition of the opex rows.

Pure — no session, no repositories, no I/O. Takes the market's opex rows (or an
already-transformed ``PreparedOpex`` dict) and returns the derived figures.

Shared by three paths that must not drift, in the same spirit as
``reference_label_resolver``:

- the seeding path (``BaseUnderwritingPayloadBuilder``), which turns these rows
  into the ``operating_expenses`` a draft underwriting is created with
- ``PrepareUwDataService``, which carries them on ``MarketContext.opex``
- the post-creation read paths, which serve them back as reference data

Row order is the contract: ``sort_order`` is stamped from list position on save,
so ``OPEX_ROWS`` decides the row order of every seeded underwriting.
"""

from decimal import Decimal
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_MONEY_QUANT = Decimal("0.01")

# --- opex column classification ---------------------------------------------
# Which columns on the opex rows are *not* monthly dollar amounts, and so are
# excluded from ``opex["absolute"]``. Each set is read back out by a caller that
# handles those columns some other way.
METADATA_FIELDS = {"id", "market_id", "market_slug", "bedrooms", "sqft"}
CLEANING_FIELDS = {"cleaning_fee", "num_of_turns"}
RANGED_FIELDS = {
    "pool_hot_tub_low",
    "pool_hot_tub_high",
    "furnishings_low",
    "furnishings_mid",
    "furnishings_high",
}
CONFIG_FIELDS = {"land_value", "appreciation"}
# Opex columns that are percentages of purchase price, not monthly dollar
# amounts; the payload builder resolves them against the listing price.
PCT_OF_PURCHASE_FIELDS = {"property_taxes"}
# Opex columns that are surfaced as amenity options (see
# PrepareUwDataService.build_amenities_options) rather than monthly opex.
AMENITY_FIELDS = {"consolidated_shipping"}

_EXCLUDED_FROM_ABSOLUTE = (
    METADATA_FIELDS
    | CLEANING_FIELDS
    | RANGED_FIELDS
    | CONFIG_FIELDS
    | AMENITY_FIELDS
    | PCT_OF_PURCHASE_FIELDS
)

# --- the row table -----------------------------------------------------------
# The seeded operating expenses, in the order the analyst sees them, each paired
# with its display label. Keys are opex columns carried on ``opex["absolute"]``,
# plus the three rows ``resolve_opex_amounts`` derives (cleaning, pool_hot_tub,
# property_taxes) and the ones with no market source at all
# (``OPEX_ROW_DEFAULTS``).
OPEX_ROWS = (
    ("internet", "Internet"),
    ("utilities", "Utilities"),
    ("pest_control", "Pest Control"),
    ("pool_hot_tub", "Pool/Hot Tub Maintenance"),
    ("outdoor_landscaping", "Outdoor/Landscaping"),
    ("software", "Software"),
    ("supplies", "Household Supplies"),
    ("cleaning", "Cleaning"),
    ("property_taxes", "Property Taxes (Monthly)"),
    ("insurance_hoi", "Insurance HOI"),
    ("capex_reserve", "CapEx Reserve"),
    ("misc", "MISC"),
    ("hoa_fees", "HOA Fees"),
)
# Rows with no opex column behind them: no market supplies them, so every
# underwriting starts from this amount and the analyst adjusts it. Merged under
# the market data in ``resolve_opex_amounts``, so adding a real column of the
# same name later would take over with no other change. Note these seed at a
# starting *value*, unlike ``ALWAYS_SEEDED_OPEX_KEYS``, which seed blank — a zero
# here renders because 0 is not None.
OPEX_ROW_DEFAULTS = {"misc": Decimal("0")}
# Seeded even when no source resolves an amount: a blank row the team fills in
# manually beats a silently absent one.
ALWAYS_SEEDED_OPEX_KEYS = frozenset({"property_taxes"})


def _money(value: Decimal) -> Decimal:
    """Round to cents, matching ``UnderwritingCalculator._money``."""
    return value.quantize(_MONEY_QUANT)


def transform_opex_costs(opex_by_bedrooms, opex_by_size) -> dict:
    """Reshape the market's opex rows into the ``PreparedOpex`` shape.

    ``opex_by_size`` wins on a key collision, matching the merge order the
    ``absolute`` bag has always used.
    """
    bedrooms_data = opex_by_bedrooms.model_dump() if opex_by_bedrooms is not None else {}
    size_data = opex_by_size.model_dump() if opex_by_size is not None else {}

    absolute = {
        k: v
        for k, v in {**bedrooms_data, **size_data}.items()
        if k not in _EXCLUDED_FROM_ABSOLUTE
    }

    return {
        "cleaning": {
            "fee": bedrooms_data.get("cleaning_fee"),
            "num_of_turns": bedrooms_data.get("num_of_turns"),
        },
        "ranged": {
            "pool_hot_tub": {
                "low": bedrooms_data.get("pool_hot_tub_low"),
                "high": bedrooms_data.get("pool_hot_tub_high"),
            },
        },
        "absolute": absolute,
        "property_tax_pct": bedrooms_data.get("property_taxes"),
    }


def build_cleaning_cost(cleaning: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve the ``uw_details.cleaning_cost`` blob from an opex cleaning dict.

    Canonical alongside ``build_opex_property_taxes``: both derive their
    uw_details blob, and the bedroom-context endpoint reuses them so a bedroom
    change hands the FE exactly the shape creation would have produced.
    """
    fee = cleaning.get("fee")
    turns = cleaning.get("num_of_turns")
    if fee is None and turns is None:
        return None

    result = {
        "cost_per_clean": fee,
        "turns_per_month": turns,
    }
    if fee is not None and turns is not None:
        result["monthly_cleaning_cost"] = fee * turns
    return result


def build_opex_property_taxes(
    *,
    property_tax_pct: Any,
    purchase_price: Decimal | None,
    zillow_annual_tax: Decimal | None = None,
) -> dict[str, Any] | None:
    """Resolve the monthly Property Taxes opex item and its breakdown.

    Sources, in priority order:
    1. Market tax rate (opex_by_bedrooms.property_taxes) x purchase price.
    2. Zillow-provided annual tax amount (not wired up yet — callers will pass
       it once it is threaded through prepared zillow data).
    3. Neither -> None; the item is seeded blank for the team to fill out.

    Amounts are annual; OPEX is monthly, so both sources divide by 12. Both are
    quantized to cents — a rate like 0.0125 would otherwise carry its own scale
    into the stored blob (0.0125 x 480000 = 6000.0000) and the division would
    trail even further. The raw figures stay recoverable under "inputs".

    Each amount is rounded from the unrounded annual, not from each other, so
    neither inherits the other's rounding error; 12 x monthly can therefore
    differ from annual by up to a cent.

    The returned dict is persisted on uw_details.property_taxes so the
    derivation stays auditable (mirrors cleaning_cost): the resolved amounts sit
    at the top level regardless of source, and the source-specific figures live
    under "inputs".
    """
    if property_tax_pct is not None and purchase_price is not None:
        pct = Decimal(str(property_tax_pct))
        annual = pct * purchase_price
        return {
            "source": "opex_property_tax_pct",
            "annual_amount": _money(annual),
            "monthly_amount": _money(annual / 12),
            "inputs": {
                "opex_property_tax_pct": pct,
                "purchase_price": purchase_price,
            },
        }
    if zillow_annual_tax is not None:
        return {
            "source": "zillow_annual_tax",
            "annual_amount": _money(zillow_annual_tax),
            "monthly_amount": _money(zillow_annual_tax / 12),
            "inputs": {},
        }
    return None


def resolve_opex_amounts(
    opex: dict[str, Any],
    property_taxes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve one monthly amount per ``OPEX_ROWS`` key.

    Defaults sit under the market data, so a real column would take over from a
    default of the same name. The three derived keys cannot collide with an
    ``absolute`` column: ``transform_opex_costs`` excludes
    cleaning_fee/num_of_turns, pool_hot_tub_low/high and property_taxes from
    ``absolute`` (see the ``*_FIELDS`` sets). They merge last regardless, so a
    future column sharing one of these names would not displace the derived row.

    A key absent from the result — or present with ``None`` — has no amount; it
    is the caller's business whether that means "drop the row" (the seeding path)
    or "return it blank" (the reference-data path).
    """
    absolute = opex.get("absolute") or {}
    cleaning = opex.get("cleaning") or {}
    fee = cleaning.get("fee")
    turns = cleaning.get("num_of_turns")
    pool_hot_tub = (opex.get("ranged") or {}).get("pool_hot_tub") or {}

    return {
        **OPEX_ROW_DEFAULTS,
        **absolute,
        "cleaning": fee * turns if fee is not None and turns is not None else None,
        "pool_hot_tub": pool_hot_tub.get("low"),
        "property_taxes": (
            property_taxes["monthly_amount"] if property_taxes else None
        ),
    }


def build_opex_expense_rows(
    opex: dict[str, Any],
    property_taxes: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Seed the monthly operating expenses in ``OPEX_ROWS`` order.

    Amounts are resolved first, then emitted in the canonical order, so the row
    order is a property of this catalog rather than of the opex table's column
    order (which is what iterating ``absolute`` gave us before).

    A row whose amount resolves to None is dropped, so the set of rows still
    follows the market data — except Property Taxes, which is always seeded so
    an unresolved amount is a blank row the team fills in rather than a missing
    one, and the ``OPEX_ROW_DEFAULTS`` rows, which no market supplies and so
    always carry their default. An opex column with no place in ``OPEX_ROWS`` is
    appended after them and logged; a newly added column should surface to the
    analyst, not disappear or land at an arbitrary position.
    """
    absolute = opex.get("absolute") or {}
    amounts = resolve_opex_amounts(opex, property_taxes)

    expenses = [
        {"expense": label, "monthly": amounts.get(key)}
        for key, label in OPEX_ROWS
        if amounts.get(key) is not None or key in ALWAYS_SEEDED_OPEX_KEYS
    ]

    placed = {key for key, _ in OPEX_ROWS}
    unplaced = [
        name
        for name, amount in absolute.items()
        if name not in placed and amount is not None
    ]
    if unplaced:
        logger.warning(
            "build_opex_expense_rows: opex columns with no canonical row",
            unplaced_opex_columns=unplaced,
        )
        expenses.extend(
            {
                "expense": humanize_expense_name(name),
                "monthly": absolute[name],
            }
            for name in unplaced
        )
    return expenses


def humanize_expense_name(value: str) -> str:
    """Fallback label for an opex column absent from ``OPEX_ROWS``."""
    return value.replace("_", " ").title()
