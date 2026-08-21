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

from app.iron_bank.enums import OpexKeyedOn
from app.iron_bank.schemas.get_underwriting import (
    GetUnderwritingOperatingExpense,
    OpexOption,
    OpexOptionInputs,
)

logger = structlog.get_logger(__name__)

_MONEY_QUANT = Decimal("0.01")

# --- opex column classification ---------------------------------------------
# Which columns on the opex rows are *not* monthly dollar amounts, and so are
# excluded from ``opex["absolute"]``. Each set is read back out by a caller that
# handles those columns some other way.
METADATA_FIELDS = {"id", "market_id", "market_slug", "bedrooms", "sqft"}
CLEANING_FIELDS = {"cleaning_fee", "num_of_turns"}
POOL_FIELDS = {"pool_hot_tub_low", "pool_hot_tub_high"}
# Surfaced as amenity price tiers (see PrepareUwDataService.FURNISHINGS_*),
# not as an opex row.
FURNISHINGS_FIELDS = {"furnishings_low", "furnishings_mid", "furnishings_high"}
RANGED_FIELDS = POOL_FIELDS | FURNISHINGS_FIELDS
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

# Which table supplies each row's figure. A property of the row table, so it
# lives next to it — and deliberately *not* derived from a fetched opex row: a
# market with no ``opex_by_size`` row (or a bedroom-context lookup, which does
# not fetch one) would then have no column names to read, and its sqft-keyed
# rows would classify as unsourced. A row's ``keyed_on`` must not depend on what
# happened to be fetched.
#
# Only the exceptions are listed; everything else is bedrooms-keyed, so a new
# ``opex_by_bedrooms`` column needs no change here. ``test_opex_catalog`` checks
# both sets against the real opex schemas, which is where a new column shows up.
_SIZE_KEYED_ROWS = frozenset({"internet", "pest_control", "utilities"})
# No market supplies these at all — they seed from OPEX_ROW_DEFAULTS and only
# ever change by hand.
_UNSOURCED_ROWS = frozenset(OPEX_ROW_DEFAULTS)


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


def keyed_on(key: str) -> OpexKeyedOn:
    """Which opex table supplies this row's figure.

    A pure function of the row key, so it answers the same way whether or not a
    market has a row at this deal's bedroom count or square footage.
    """
    if key in _SIZE_KEYED_ROWS:
        return OpexKeyedOn.SIZE
    if key in _UNSOURCED_ROWS:
        return OpexKeyedOn.NONE
    return OpexKeyedOn.BEDROOMS


def _row_inputs(key: str, opex: dict[str, Any]) -> OpexOptionInputs | None:
    """The drivers behind the three rows that aren't a single market figure."""
    if key == "cleaning":
        cleaning = opex.get("cleaning") or {}
        return OpexOptionInputs(
            cost_per_clean=cleaning.get("fee"),
            turns_per_month=cleaning.get("num_of_turns"),
        )
    if key == "pool_hot_tub":
        pool_hot_tub = (opex.get("ranged") or {}).get("pool_hot_tub") or {}
        return OpexOptionInputs(
            low=pool_hot_tub.get("low"), high=pool_hot_tub.get("high")
        )
    if key == "property_taxes":
        return OpexOptionInputs(pct=opex.get("property_tax_pct"))
    return None


def build_opex_options(
    *,
    opex_by_bedrooms,
    opex_by_size,
    purchase_price: Decimal | None = None,
) -> list[OpexOption]:
    """The full operating-expense catalog for one market/bedrooms/sqft.

    Every ``OPEX_ROWS`` row is returned, in canonical order, including the ones
    the market supplies no figure for — a null amount is information ("this row
    exists, the market has no number for it"), and dropping it would leave the
    client unable to tell that from a row that does not exist.

    ``purchase_price`` only affects the Property Taxes row, whose market figure
    is a rate rather than an amount; without one that row's ``monthly_amount``
    is null while ``inputs.pct`` still carries the rate.

    Unlike ``build_opex_expense_rows`` this does not append unplaced columns: a
    column missing from ``OPEX_ROWS`` has no key or label to offer a client, and
    the seeding path already logs it.
    """
    opex = transform_opex_costs(opex_by_bedrooms, opex_by_size)
    property_taxes = build_opex_property_taxes(
        property_tax_pct=opex.get("property_tax_pct"),
        purchase_price=purchase_price,
    )
    amounts = resolve_opex_amounts(opex, property_taxes)

    return [
        OpexOption(
            key=key,
            expense_name=label,
            monthly_amount=amounts.get(key),
            keyed_on=keyed_on(key),
            inputs=_row_inputs(key, opex),
        )
        for key, label in OPEX_ROWS
    ]


def resolve_opex_updates(
    options: list[OpexOption],
    existing_expenses,
) -> list[GetUnderwritingOperatingExpense]:
    """Re-point catalog figures at an underwriting's own expense rows.

    The one place a catalog row is matched to a ledger row. Matching is by
    ``expense_name``, which holds because the FE does not expose the label for
    editing — but the API does accept it, so this is the single function that
    breaks if that ever changes, rather than every client that merges a patch.

    A row the deal does not have comes back with ``id=None``, meaning "insert
    this": the analyst deleted it, or the deal predates the column.
    ``_upsert_children`` already treats an unmatched id as an insert, so a client
    can PUT the result straight back.

    Rows whose ``monthly_amount`` is null are dropped — there is no new figure
    to apply, and emitting them would blank a number the analyst can see.
    """
    by_name = {}
    for expense in existing_expenses or []:
        # First occurrence wins: nothing stops two rows sharing a label, and the
        # earlier one is the seeded row.
        by_name.setdefault(expense.expense_name, expense)

    updates = []
    unmatched = []
    for option in options:
        if option.monthly_amount is None:
            continue
        existing = by_name.get(option.expense_name)
        if existing is None:
            unmatched.append(option.expense_name)
        updates.append(
            GetUnderwritingOperatingExpense(
                id=existing.id if existing is not None else None,
                expense_name=option.expense_name,
                monthly_amount=option.monthly_amount,
            )
        )

    if unmatched:
        logger.warning(
            "resolve_opex_updates: catalog rows absent from the underwriting",
            unmatched_expense_names=unmatched,
        )
    return updates
