from decimal import Decimal
from typing import Any

import structlog

from app.iron_bank.enums import DealStatus
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService
from app.iron_bank.services.purchase_price_reconciliation_payload_builder import (
    PurchasePriceReconciliationPayloadBuilder,
)

logger = structlog.get_logger(__name__)


class BaseUnderwritingPayloadBuilder:
    """Shared default-seeding logic for underwriting payload builders.

    Holds the financing/tax defaults and the helpers that both the automated
    (``UnderwritingPayloadBuilder``) and non-automated
    (``NonAutomatedUnderwritingPayloadBuilder``) flows use to seed a draft
    underwriting: financing/tax terms, and — for any flow that has market
    context — the operating-expense and rehab line items derived from it. It
    does not fetch data or persist anything.
    """

    _DEFAULT_DEAL_STATUS = DealStatus.TEMPLATE_GENERATED
    _DEFAULT_SLA_MULTIPLIER_PCT = Decimal("0.36")
    _DEFAULT_BONUS_AMOUNT_PCT = Decimal("1")
    _MONEY_QUANT = Decimal("0.01")

    # Seeded optimization items all price at tier 2 for now; the analyst
    # re-tiers from the amenity catalog in the edit form.
    _AMENITY_PRICE_TIER_FIELD = "price_tier_2"
    _AMENITY_TIER_LABEL = "Mid"
    _AMENITY_METRIC = "flat"
    _POOL_AMENITY_IDS_TO_EXCLUDE = {4, 5, 13, 14}

    # The seeded options bracket the market's must-have amenities: furnishings
    # opens the rehab budget, the two service lines close it out. Same three ids
    # as PrepareUwDataService.SEEDED_AMENITY_OPTION_IDS, which is a membership
    # set (see to_template_market_context) and says nothing about order — the
    # order lives here, because it is a property of the seeded payload.
    _LEADING_AMENITY_OPTION_IDS = (PrepareUwDataService.FURNISHINGS_OPTION_ID,)
    _TRAILING_AMENITY_OPTION_IDS = (
        PrepareUwDataService.STR_CRIBS_PROJECT_MANAGEMENT_OPTION_ID,
        PrepareUwDataService.CONSOLIDATED_SHIPPING_OPTION_ID,
    )

    # The seeded operating expenses, in the order the analyst sees them, each
    # paired with its display label. Keys are opex columns carried on
    # ``opex["absolute"]``, plus the three rows _build_operating_expenses
    # derives (cleaning, pool_hot_tub, property_taxes). Order is the contract:
    # sort_order is stamped from list position on save, so this tuple decides
    # the row order of every seeded underwriting.
    _OPEX_ROWS = (
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
        ("hoa_fees", "HOA Fees"),
    )
    # Seeded even when no source resolves an amount: a blank row the team fills
    # in manually beats a silently absent one.
    _ALWAYS_SEEDED_OPEX_KEYS = frozenset({"property_taxes"})

    def _resolve_owner_id(
        self, context: dict[str, Any], *, fallback_user_id: int | None = None
    ) -> int | None:
        """Pick the owner for a draft underwriting.

        The market's analyst owner (``market_keys_master.analyst_owner_id``,
        carried on the market context) wins. ``fallback_user_id`` covers the
        non-automated flow, where a market-less deal — or a market with no
        analyst assigned — is owned by whoever created it.
        """
        return context.get("analyst_owner_id") or fallback_user_id

    def _build_details(
        self,
        *,
        purchase_price: Decimal | None,
        config: dict[str, Any],
        cleaning_cost: dict[str, Any] | None,
        property_taxes: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        detail: dict[str, Any] = {}
        if purchase_price is not None:
            detail["purchase_details"] = {
                "purchase_price": purchase_price,
                "down_payment_pct": self._decimal_or_default(
                    config.get("down_payment"), Decimal("0.1")
                ),
                "interest_rate": self._decimal_or_default(
                    config.get("interest_rate"), Decimal("0.0688")
                ),
                "mortgage_years": int(config.get("loan_term_years") or 30),
                "closing_costs_pct": self._decimal_or_default(
                    config.get("closing_costs"), Decimal("0.03")
                ),
            }
        if cleaning_cost is not None:
            detail["cleaning_cost"] = cleaning_cost
        if property_taxes is not None:
            detail["property_taxes"] = property_taxes
        return detail or None

    def _build_taxes(self, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "land_assumptions_pct": self._decimal_or_default(
                config.get("land_assumptions"), Decimal("0.2")
            ),
            "sla_multiplier_pct": self._decimal_or_default(
                config.get("sla_multiplier_pct"), self._DEFAULT_SLA_MULTIPLIER_PCT
            ),
            "bonus_amount_pct": self._decimal_or_default(
                config.get("bonus_amount_pct"), self._DEFAULT_BONUS_AMOUNT_PCT
            ),
            "tax_rate_pct": self._decimal_or_default(
                config.get("tax_rate"), Decimal("0.37")
            ),
        }

    def build_opex_property_taxes(
        self,
        *,
        property_tax_pct: Any,
        purchase_price: Decimal | None,
        zillow_annual_tax: Decimal | None = None,
    ) -> dict[str, Any] | None:
        """Resolve the monthly Property Taxes opex item and its breakdown.

        Sources, in priority order:
        1. Market tax rate (opex_by_bedrooms.property_taxes) x purchase price.
        2. Zillow-provided annual tax amount (not wired up yet — callers will
           pass it once it is threaded through prepared zillow data).
        3. Neither -> None; the item is seeded blank for the team to fill out.

        Amounts are annual; OPEX is monthly, so both sources divide by 12.
        Both are quantized to cents — a rate like 0.0125 would otherwise carry
        its own scale into the stored blob (0.0125 x 480000 = 6000.0000) and the
        division would trail even further. The raw figures stay recoverable
        under "inputs".

        Each amount is rounded from the unrounded annual, not from each other,
        so neither inherits the other's rounding error; 12 x monthly can
        therefore differ from annual by up to a cent.

        The returned dict is persisted on uw_details.property_taxes so the
        derivation stays auditable (mirrors cleaning_cost): the resolved
        amounts sit at the top level regardless of source, and the
        source-specific figures live under "inputs".
        """
        if property_tax_pct is not None and purchase_price is not None:
            pct = Decimal(str(property_tax_pct))
            annual = pct * purchase_price
            return {
                "source": "opex_property_tax_pct",
                "annual_amount": self._money(annual),
                "monthly_amount": self._money(annual / 12),
                "inputs": {
                    "opex_property_tax_pct": pct,
                    "purchase_price": purchase_price,
                },
            }
        if zillow_annual_tax is not None:
            return {
                "source": "zillow_annual_tax",
                "annual_amount": self._money(zillow_annual_tax),
                "monthly_amount": self._money(zillow_annual_tax / 12),
                "inputs": {},
            }
        return None

    def _money(self, value: Decimal) -> Decimal:
        """Round to cents, matching ``UnderwritingCalculator._money``."""
        return value.quantize(self._MONEY_QUANT)

    def _build_optimization_list(
        self, context: dict[str, Any], *, zpid: Any = None
    ) -> list[dict[str, Any]]:
        """Seed the rehab budget from the amenity options prepared for this deal.

        ``context`` is a dumped ``MarketContext`` (the automated flow's prepared
        result is one). The seeded options bracket the market's must-have
        amenities: furnishings first, then the must-haves in the order the market
        lists them, then the STR Cribs management fee and consolidated shipping.
        Items whose tier-2 price is missing are still seeded with a blank amount —
        a visible row the analyst fills in beats a silently absent line item.
        """
        options_by_id = {
            option.get("id"): option
            for option in context.get("construction_amenities") or []
        }
        # Seeded ids are dropped from the must-haves rather than left to
        # dict.fromkeys below: that keeps the first occurrence of a duplicate, so
        # a must-have naming a trailing option would pull it up out of its
        # bracket. Catalog ids are positive and the seeded sentinels are not, so
        # this cannot happen today — filtering makes the bracket unconditional
        # instead of a coincidence of the id ranges.
        must_have_ids = [
            id
            for id in (context.get("must_have_amenity_ids") or [])
            if id not in self._POOL_AMENITY_IDS_TO_EXCLUDE
            and id not in PrepareUwDataService.SEEDED_AMENITY_OPTION_IDS
        ]
        selected_ids = list(
            dict.fromkeys(
                [
                    *self._LEADING_AMENITY_OPTION_IDS,
                    *must_have_ids,
                    *self._TRAILING_AMENITY_OPTION_IDS,
                ]
            )
        )

        unknown_ids = [
            amenity_id for amenity_id in selected_ids if amenity_id not in options_by_id
        ]
        if unknown_ids:
            logger.warning(
                "_build_optimization_list: amenity ids absent from the catalog",
                zpid=zpid,
                market_id=context.get("market_id"),
                unknown_amenity_ids=unknown_ids,
            )

        return [
            self._amenity_to_optimization_item(options_by_id[amenity_id])
            for amenity_id in selected_ids
            if amenity_id in options_by_id
        ]

    def _amenity_to_optimization_item(self, option: dict[str, Any]) -> dict[str, Any]:
        price = option.get(self._AMENITY_PRICE_TIER_FIELD)
        return {
            "category": option.get("amenity_name"),
            "total_price": price,
            "base_price": price,
            "metric": self._AMENITY_METRIC,
            "tier": self._AMENITY_TIER_LABEL,
        }

    def build_cleaning_cost(self, cleaning: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve the uw_details.cleaning_cost blob from an opex cleaning dict.

        Public alongside ``build_opex_property_taxes``: both are the canonical
        derivations for their uw_details blob, and the bedroom-context endpoint
        reuses them so a bedroom change hands the FE exactly the shape creation
        would have produced.
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

    def _build_operating_expenses(
        self,
        opex: dict[str, Any],
        property_taxes: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Seed the monthly operating expenses in ``_OPEX_ROWS`` order.

        Amounts are resolved first, then emitted in the canonical order, so the
        row order is a property of this builder rather than of the opex table's
        column order (which is what iterating ``absolute`` gave us before).

        A row whose amount resolves to None is dropped, so the set of rows still
        follows the market data — except Property Taxes, which is always seeded
        so an unresolved amount is a blank row the team fills in rather than a
        missing one. An opex column with no place in ``_OPEX_ROWS`` is appended
        after them and logged; a newly added column should surface to the
        analyst, not disappear or land at an arbitrary position.
        """
        absolute = opex.get("absolute") or {}
        cleaning = opex.get("cleaning") or {}
        fee = cleaning.get("fee")
        turns = cleaning.get("num_of_turns")
        pool_hot_tub = (opex.get("ranged") or {}).get("pool_hot_tub") or {}

        # The three derived keys cannot collide with an `absolute` column:
        # PrepareUwDataService excludes cleaning_fee/num_of_turns,
        # pool_hot_tub_low/high and property_taxes from `absolute` (see its
        # _OPEX_*_FIELDS sets). They merge last regardless, so a future column
        # sharing one of these names would not displace the derived row.
        amounts: dict[str, Any] = {
            **absolute,
            "cleaning": fee * turns if fee is not None and turns is not None else None,
            "pool_hot_tub": pool_hot_tub.get("low"),
            "property_taxes": (
                property_taxes["monthly_amount"] if property_taxes else None
            ),
        }

        expenses = [
            {"expense": label, "monthly": amounts.get(key)}
            for key, label in self._OPEX_ROWS
            if amounts.get(key) is not None or key in self._ALWAYS_SEEDED_OPEX_KEYS
        ]

        placed = {key for key, _ in self._OPEX_ROWS}
        unplaced = [
            name
            for name, amount in absolute.items()
            if name not in placed and amount is not None
        ]
        if unplaced:
            logger.warning(
                "_build_operating_expenses: opex columns with no canonical row",
                unplaced_opex_columns=unplaced,
            )
            expenses.extend(
                {
                    "expense": self._humanize_expense_name(name),
                    "monthly": absolute[name],
                }
                for name in unplaced
            )
        return expenses

    def _humanize_expense_name(self, value: str) -> str:
        """Fallback label for an opex column absent from ``_OPEX_ROWS``."""
        return value.replace("_", " ").title()

    @staticmethod
    def _as_int(value: Any) -> int | None:
        """Coerce a Zillow-supplied number to int, or None if it isn't one.

        Mirrors ``CreateUnderwritingFromUrlService._as_int``: the live Zillow
        fetch can report bedrooms as a float, unlike ``scheduled_listings.beds``.
        """
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _money_to_decimal(self, value: Any) -> Decimal | None:
        return PurchasePriceReconciliationPayloadBuilder.normalize_purchase_price(value)

    def _decimal_or_default(self, value: Any, default: Decimal) -> Decimal:
        if value is None:
            return default
        return Decimal(str(value))
