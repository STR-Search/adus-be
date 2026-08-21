from decimal import Decimal

from app.iron_bank.services.base_underwriting_payload_builder import (
    BaseUnderwritingPayloadBuilder,
)
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService


def _builder():
    return BaseUnderwritingPayloadBuilder()


def _option(option_id: int, name: str, price=1000) -> dict:
    return {"id": option_id, "amenity_name": name, "price_tier_2": price}


class TestOperatingExpenseOrder:
    """The rows follow opex_catalog.OPEX_ROWS, not the opex table's column
    order, and sort_order is stamped from these positions on save.

    Exercised through the builder's delegation rather than against the catalog
    directly: what matters here is that the seeded payload still comes out in
    the canonical order."""

    # Deliberately in a different order than OPEX_ROWS: the builder must not
    # inherit the order the opex columns happen to arrive in.
    _ABSOLUTE = {
        "outdoor_landscaping": Decimal("150"),
        "software": Decimal("50"),
        "insurance_hoi": Decimal("200"),
        "supplies": Decimal("75"),
        "capex_reserve": Decimal("300"),
        "hoa_fees": Decimal("125"),
        "internet": Decimal("100"),
        "pest_control": Decimal("60"),
        "utilities": Decimal("350"),
    }

    def _opex(self, **overrides):
        return {
            "cleaning": {"fee": Decimal("275"), "num_of_turns": Decimal("4")},
            "ranged": {"pool_hot_tub": {"low": Decimal("125")}},
            "absolute": dict(self._ABSOLUTE),
            **overrides,
        }

    # Sentinel, so a test can pass property_taxes=None to mean "unresolved"
    # rather than "use the default".
    _UNSET = object()

    def _expenses(self, opex=None, property_taxes=_UNSET):
        return _builder()._build_operating_expenses(
            opex if opex is not None else self._opex(),
            {"monthly_amount": Decimal("485")}
            if property_taxes is self._UNSET
            else property_taxes,
        )

    def test_rows_are_emitted_in_the_canonical_order(self):
        assert [expense["expense"] for expense in self._expenses()] == [
            "Internet",
            "Utilities",
            "Pest Control",
            "Pool/Hot Tub Maintenance",
            "Outdoor/Landscaping",
            "Software",
            "Household Supplies",
            "Cleaning",
            "Property Taxes (Monthly)",
            "Insurance HOI",
            "CapEx Reserve",
            "MISC",
            "HOA Fees",
        ]

    def test_labels_carry_the_resolved_amounts(self):
        by_expense = {e["expense"]: e["monthly"] for e in self._expenses()}

        assert by_expense["Household Supplies"] == Decimal("75")
        assert by_expense["Insurance HOI"] == Decimal("200")
        assert by_expense["HOA Fees"] == Decimal("125")
        assert by_expense["Pool/Hot Tub Maintenance"] == Decimal("125")
        assert by_expense["Cleaning"] == Decimal("1100")  # 275 x 4 turns
        assert by_expense["Property Taxes (Monthly)"] == Decimal("485")

    def test_unresolved_rows_are_dropped_but_the_order_holds(self):
        opex = self._opex(
            cleaning={},
            ranged={},
            absolute={"utilities": Decimal("350"), "hoa_fees": Decimal("125")},
        )

        assert [e["expense"] for e in self._expenses(opex=opex)] == [
            "Utilities",
            "Property Taxes (Monthly)",
            "MISC",
            "HOA Fees",
        ]

    def test_misc_is_seeded_at_zero_with_no_market_source(self):
        # No opex column supplies MISC, so it is seeded from
        # OPEX_ROW_DEFAULTS on every underwriting — including one whose
        # market data is entirely absent.
        opex = self._opex(cleaning={}, ranged={}, absolute={})
        expenses = self._expenses(opex=opex, property_taxes=None)

        assert [e["expense"] for e in expenses] == [
            "Property Taxes (Monthly)",
            "MISC",
        ]
        # zero, not blank: MISC starts at an amount, Property Taxes at nothing
        assert expenses[0]["monthly"] is None
        assert expenses[1]["monthly"] == Decimal("0")

    def test_a_market_column_would_override_a_default(self):
        # Migration path: if misc ever becomes a real opex column, the market
        # value takes over with no change to OPEX_ROWS.
        opex = self._opex(cleaning={}, ranged={}, absolute={"misc": Decimal("250")})
        by_expense = {e["expense"]: e["monthly"] for e in self._expenses(opex=opex)}

        assert by_expense["MISC"] == Decimal("250")

    def test_property_taxes_holds_its_position_when_blank(self):
        expenses = self._expenses(property_taxes=None)
        blank = next(e for e in expenses if e["expense"] == "Property Taxes (Monthly)")

        assert blank["monthly"] is None
        # 9th of thirteen, exactly where a resolved amount would sit
        assert expenses.index(blank) == 8

    def test_cleaning_needs_both_a_fee_and_turns(self):
        opex = self._opex(cleaning={"fee": Decimal("275")}, absolute={})

        assert [e["expense"] for e in self._expenses(opex=opex)] == [
            "Pool/Hot Tub Maintenance",
            "Property Taxes (Monthly)",
            "MISC",
        ]

    def test_an_unplaced_opex_column_is_appended_last(self):
        # A column added to the opex table but not to OPEX_ROWS still reaches
        # the analyst, humanized, after every canonical row.
        opex = self._opex(
            cleaning={},
            ranged={},
            absolute={"snow_removal": Decimal("80"), "utilities": Decimal("350")},
        )

        assert [e["expense"] for e in self._expenses(opex=opex)] == [
            "Utilities",
            "Property Taxes (Monthly)",
            "MISC",
            "Snow Removal",
        ]

    def test_an_unplaced_column_with_no_amount_is_not_seeded(self):
        opex = self._opex(cleaning={}, ranged={}, absolute={"snow_removal": None})

        assert [e["expense"] for e in self._expenses(opex=opex)] == [
            "Property Taxes (Monthly)",
            "MISC",
        ]


class TestOptimizationListOrder:
    """The seeded rows bracket the must-haves, and sort_order is stamped from
    this list's positions on save, so the order is the contract."""

    _CATALOG = [
        _option(PrepareUwDataService.FURNISHINGS_OPTION_ID, "Furnishings"),
        _option(PrepareUwDataService.CONSOLIDATED_SHIPPING_OPTION_ID, "Shipping"),
        _option(
            PrepareUwDataService.STR_CRIBS_PROJECT_MANAGEMENT_OPTION_ID, "Project Mgmt"
        ),
        _option(1, "Hot Tub"),
        _option(2, "Fire Pit"),
        _option(3, "Sauna"),
    ]

    def _categories(self, must_have_amenity_ids: list[int]) -> list[str]:
        items = _builder()._build_optimization_list(
            {
                "construction_amenities": self._CATALOG,
                "must_have_amenity_ids": must_have_amenity_ids,
            }
        )
        return [item["category"] for item in items]

    def test_must_haves_sit_between_furnishings_and_the_service_lines(self):
        # Several must-haves, so the order within the middle block is pinned too:
        # it follows the order the market lists them, not the catalog's.
        assert self._categories([3, 1, 2]) == [
            "Furnishings",
            "Sauna",
            "Hot Tub",
            "Fire Pit",
            "Project Mgmt",
            "Shipping",
        ]

    def test_the_bracket_holds_with_no_must_haves(self):
        assert self._categories([]) == ["Furnishings", "Project Mgmt", "Shipping"]

    def test_a_must_have_naming_a_seeded_option_stays_in_its_bracket(self):
        # Can't happen with today's ids (catalog ids are positive, the seeded
        # sentinels are not), but the bracket must not depend on that.
        assert self._categories(
            [
                PrepareUwDataService.CONSOLIDATED_SHIPPING_OPTION_ID,
                1,
                PrepareUwDataService.FURNISHINGS_OPTION_ID,
            ]
        ) == ["Furnishings", "Hot Tub", "Project Mgmt", "Shipping"]

    def test_every_seeded_option_is_placed_in_the_bracket(self):
        # Guards drift: a fourth synthetic option added to the prepare service
        # would otherwise be silently left out of the seeded payload.
        builder = BaseUnderwritingPayloadBuilder
        assert set(
            builder._LEADING_AMENITY_OPTION_IDS + builder._TRAILING_AMENITY_OPTION_IDS
        ) == set(PrepareUwDataService.SEEDED_AMENITY_OPTION_IDS)
