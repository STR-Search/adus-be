from decimal import Decimal
from types import SimpleNamespace

from app.iron_bank.enums import OpexKeyedOn
from app.iron_bank.schemas.prepare_uw import PreparedOpex
from app.iron_bank.services import opex_catalog
from app.markets.schemas.opex import OpexByBedroomsSchema, OpexBySizeSchema


def _bedrooms_row(**overrides):
    values = dict(
        id=7,
        market_id=3,
        bedrooms=4,
        cleaning_fee=Decimal("225"),
        num_of_turns=Decimal("6.5"),
        property_taxes=Decimal("0.01"),
        pool_hot_tub_low=Decimal("125"),
        pool_hot_tub_high=Decimal("275"),
        pool_and_hot_tub=Decimal("350"),
        outdoor_landscaping=Decimal("150"),
        software=Decimal("50"),
        insurance_hoi=Decimal("300"),
        supplies=Decimal("205"),
        capex_reserve=Decimal("400"),
        hoa_fees=Decimal("0"),
        furnishings_low=Decimal("67500"),
        furnishings_high=Decimal("75000"),
        consolidated_shipping=Decimal("18225"),
        land_value=Decimal("0.16"),
        appreciation=Decimal("0.0425"),
    )
    values.update(overrides)
    return OpexByBedroomsSchema.model_validate(values)


def _size_row(**overrides):
    values = dict(
        id=11,
        market_id=3,
        sqft=2000,
        internet=Decimal("100"),
        pest_control=Decimal("60"),
        utilities=Decimal("600"),
    )
    values.update(overrides)
    return OpexBySizeSchema.model_validate(values)


def _options(**kwargs):
    kwargs.setdefault("opex_by_bedrooms", _bedrooms_row())
    kwargs.setdefault("opex_by_size", _size_row())
    kwargs.setdefault("purchase_price", Decimal("450000"))
    return opex_catalog.build_opex_options(**kwargs)


def _by_key(options):
    return {option.key: option for option in options}


class TestBuildOpexOptions:
    def test_every_canonical_row_is_returned_in_order(self):
        # The catalog is the row table, so it must not be filtered by what a
        # given market happens to supply — a client cannot tell "no figure" from
        # "no such row" if absent rows are dropped.
        assert [option.key for option in _options()] == [
            key for key, _ in opex_catalog.OPEX_ROWS
        ]

    def test_labels_match_the_seeded_rows(self):
        # Shared-source invariant: the catalog and the seeding path read the same
        # table, so a client can join a catalog row to a seeded row by label.
        catalog_labels = {option.expense_name for option in _options()}
        seeded_labels = {label for _, label in opex_catalog.OPEX_ROWS}

        assert catalog_labels == seeded_labels

    def test_amounts_come_off_the_market_rows(self):
        by_key = _by_key(_options())

        assert by_key["internet"].monthly_amount == Decimal("100")
        assert by_key["utilities"].monthly_amount == Decimal("600")
        assert by_key["insurance_hoi"].monthly_amount == Decimal("300")
        # the low end of the range seeds the row
        assert by_key["pool_hot_tub"].monthly_amount == Decimal("125")
        # 225 x 6.5 turns
        assert by_key["cleaning"].monthly_amount == Decimal("1462.5")
        # 0.01 x 450000 / 12
        assert by_key["property_taxes"].monthly_amount == Decimal("375.00")

    def test_a_row_with_no_market_figure_is_returned_null_not_dropped(self):
        by_key = _by_key(_options(opex_by_size=None))

        assert by_key["internet"].monthly_amount is None
        assert by_key["utilities"].monthly_amount is None
        # zero is a figure, not an absence
        assert by_key["hoa_fees"].monthly_amount == Decimal("0")

    def test_misc_carries_its_default_with_no_market_behind_it(self):
        assert _by_key(_options())["misc"].monthly_amount == Decimal("0")


class TestBuildOpexExpenseRows:
    """The seeding path emits the same row set the catalog does.

    Both read ``OPEX_ROWS`` through ``resolve_opex_amounts``, so a seeded deal
    and the catalog it is edited against cannot disagree about which rows exist
    — only about what they are worth.
    """

    def _rows(self, opex_by_bedrooms=None, opex_by_size=None, **kwargs):
        opex = opex_catalog.transform_opex_costs(opex_by_bedrooms, opex_by_size)
        return opex_catalog.build_opex_expense_rows(opex, **kwargs)

    def test_every_canonical_row_is_seeded_in_order(self):
        rows = self._rows(_bedrooms_row(), _size_row())

        assert [row["expense"] for row in rows] == [
            label for _, label in opex_catalog.OPEX_ROWS
        ]

    def test_the_row_set_does_not_depend_on_the_market_data(self):
        # The point of the change: an underwriting seeded with nothing resolved
        # still carries every row, so the analyst sees a blank to fill in rather
        # than an expense that silently does not exist. A market-less, bedroom-
        # less deal is the worst case and it still gets the full set.
        assert [row["expense"] for row in self._rows()] == [
            label for _, label in opex_catalog.OPEX_ROWS
        ]

    def test_an_unresolved_amount_is_null_not_zero(self):
        # Null and zero are different claims — "nobody has a figure" versus "the
        # figure is nothing" — and only misc is entitled to the second.
        by_name = {row["expense"]: row["monthly"] for row in self._rows()}

        assert by_name["Internet"] is None
        assert by_name["Cleaning"] is None
        assert by_name["Property Taxes (Monthly)"] is None
        assert by_name["MISC"] == Decimal("0")

    def test_an_unplaced_column_is_still_appended_after_the_canonical_rows(self):
        # Injected into ``absolute`` directly: the opex schemas drop a field they
        # do not declare, so a column new enough to have no canonical row cannot
        # be staged through them.
        opex = opex_catalog.transform_opex_costs(_bedrooms_row(), _size_row())
        opex["absolute"]["unknown_new_column"] = Decimal("42")

        rows = opex_catalog.build_opex_expense_rows(opex)
        labels = [row["expense"] for row in rows]

        assert labels[: len(opex_catalog.OPEX_ROWS)] == [
            label for _, label in opex_catalog.OPEX_ROWS
        ]
        assert rows[-1] == {"expense": "Unknown New Column", "monthly": Decimal("42")}


class TestPoolColumnsAreNotRowsOfTheirOwn:
    """The pool/hot tub family feeds one row, not one row each.

    A pool column missing from ``POOL_FIELDS`` lands in ``absolute``, and
    ``build_opex_expense_rows`` then seeds it as an extra expense row with a
    humanized label. The classification is a hand-kept set, so this is the
    guard: nothing in ``POOL_FIELDS`` may reach either place.
    """

    def _opex(self):
        return opex_catalog.transform_opex_costs(_bedrooms_row(), _size_row())

    def test_no_pool_column_reaches_the_absolute_bag(self):
        # Named rather than read off POOL_FIELDS: comparing the set against
        # itself would pass however the classification drifts.
        absolute = self._opex()["absolute"]

        assert "pool_and_hot_tub" not in absolute
        assert "pool_hot_tub_low" not in absolute
        assert "pool_hot_tub_high" not in absolute

    def test_no_pool_column_is_seeded_as_an_expense_row_of_its_own(self):
        rows = opex_catalog.build_opex_expense_rows(self._opex())
        names = {row["expense"] for row in rows}

        assert "Pool And Hot Tub" not in names
        assert names <= {label for _, label in opex_catalog.OPEX_ROWS}

    def test_the_combined_figure_survives_the_prepared_opex_schema(self):
        # PreparedOpex drops keys it does not declare, so a figure carried by
        # transform_opex_costs but absent from the schema would vanish on the
        # MarketContext path without failing anywhere.
        prepared = PreparedOpex.model_validate(self._opex())

        assert prepared.ranged.pool_hot_tub.pool_and_hot_tub == Decimal("350")


class TestKeyedOn:
    """Which rows a bedroom or sqft change would re-seed."""

    def test_rows_are_classified_by_the_table_that_supplied_them(self):
        by_key = _by_key(_options())
        keyed_on = {key: option.keyed_on for key, option in by_key.items()}

        assert keyed_on == {
            "internet": OpexKeyedOn.SIZE,
            "utilities": OpexKeyedOn.SIZE,
            "pest_control": OpexKeyedOn.SIZE,
            "pool_hot_tub": OpexKeyedOn.BEDROOMS,
            "outdoor_landscaping": OpexKeyedOn.BEDROOMS,
            "software": OpexKeyedOn.BEDROOMS,
            "supplies": OpexKeyedOn.BEDROOMS,
            "cleaning": OpexKeyedOn.BEDROOMS,
            "property_taxes": OpexKeyedOn.BEDROOMS,
            "insurance_hoi": OpexKeyedOn.BEDROOMS,
            "capex_reserve": OpexKeyedOn.BEDROOMS,
            "misc": OpexKeyedOn.NONE,
            "hoa_fees": OpexKeyedOn.BEDROOMS,
        }

    def test_the_derived_rows_follow_their_source_columns(self):
        # cleaning, pool_hot_tub and property_taxes are not columns — they are
        # derived from columns, and must still classify as bedrooms-keyed.
        by_key = _by_key(_options())

        for key in ("cleaning", "pool_hot_tub", "property_taxes"):
            assert by_key[key].keyed_on is OpexKeyedOn.BEDROOMS

    def test_classification_survives_a_missing_size_row(self):
        # No size row means no sqft-keyed figures, but the rows still exist and
        # are still sqft-keyed — a bedroom change must not claim them.
        by_key = _by_key(_options(opex_by_size=None))

        assert by_key["internet"].keyed_on is OpexKeyedOn.SIZE
        assert by_key["insurance_hoi"].keyed_on is OpexKeyedOn.BEDROOMS

    def test_classification_is_independent_of_what_was_fetched(self):
        # keyed_on describes the row, not this lookup. Fetching neither row must
        # not turn every row into "no market source".
        assert opex_catalog.keyed_on("internet") is OpexKeyedOn.SIZE
        assert opex_catalog.keyed_on("insurance_hoi") is OpexKeyedOn.BEDROOMS
        assert opex_catalog.keyed_on("misc") is OpexKeyedOn.NONE

    def test_every_row_matches_the_table_that_actually_has_the_column(self):
        # The classification is a hand-kept exception list, so this is the guard
        # against drift: a column added to either opex table, or a row whose
        # source moves between them, fails here.
        bedrooms_columns = set(OpexByBedroomsSchema.model_fields)
        size_columns = set(OpexBySizeSchema.model_fields)
        # The rows that are derived rather than read straight off a column,
        # mapped to the column each is derived from.
        derived = {
            "cleaning": "cleaning_fee",
            "pool_hot_tub": "pool_hot_tub_low",
            "property_taxes": "property_taxes",
        }

        for key, _ in opex_catalog.OPEX_ROWS:
            column = derived.get(key, key)
            expected = (
                OpexKeyedOn.SIZE
                if column in size_columns
                else OpexKeyedOn.BEDROOMS
                if column in bedrooms_columns
                else OpexKeyedOn.NONE
            )
            assert opex_catalog.keyed_on(key) is expected, key


class TestRowInputs:
    def test_only_the_three_derived_rows_carry_inputs(self):
        with_inputs = {
            option.key for option in _options() if option.inputs is not None
        }

        assert with_inputs == {"cleaning", "pool_hot_tub", "property_taxes"}

    def test_cleaning_exposes_its_two_drivers(self):
        inputs = _by_key(_options())["cleaning"].inputs

        assert inputs.cost_per_clean == Decimal("225")
        assert inputs.turns_per_month == Decimal("6.5")
        assert inputs.low is None and inputs.pct is None

    def test_pool_hot_tub_exposes_both_ends_of_the_range(self):
        inputs = _by_key(_options())["pool_hot_tub"].inputs

        assert inputs.low == Decimal("125")
        assert inputs.high == Decimal("275")

    def test_pool_hot_tub_exposes_the_combined_figure_without_seeding_from_it(self):
        # All three candidates for the row reach the client; only the low end
        # drives the amount until a later change picks between them.
        option = _by_key(_options())["pool_hot_tub"]

        assert option.inputs.pool_and_hot_tub == Decimal("350")
        assert option.monthly_amount == Decimal("125")

    def test_property_taxes_exposes_the_rate_even_with_no_price(self):
        # The rate is market data and is worth showing; only the amount depends
        # on a purchase price the deal may not have yet.
        option = _by_key(_options(purchase_price=None))["property_taxes"]

        assert option.monthly_amount is None
        assert option.inputs.pct == Decimal("0.01")


class TestResolveOpexUpdates:
    """The one place a catalog row is matched to an underwriting's own row."""

    def _expense(self, expense_id, expense_name):
        return SimpleNamespace(
            id=expense_id, expense_name=expense_name, monthly_amount=Decimal("1")
        )

    def _bedroom_keyed(self):
        return [
            option
            for option in _options(opex_by_size=None)
            if option.keyed_on is OpexKeyedOn.BEDROOMS
        ]

    def test_updates_carry_the_matched_rows_ids(self):
        ledger = [
            self._expense(8808, "Cleaning"),
            self._expense(8810, "Insurance HOI"),
        ]

        updates = opex_catalog.resolve_opex_updates(self._bedroom_keyed(), ledger)
        by_name = {u.expense_name: u.id for u in updates}

        assert by_name["Cleaning"] == 8808
        assert by_name["Insurance HOI"] == 8810

    def test_an_unmatched_row_comes_back_as_an_insert(self):
        # The analyst deleted this row, or the deal predates the column. None is
        # what _upsert_children already treats as an insert.
        updates = opex_catalog.resolve_opex_updates(
            self._bedroom_keyed(), [self._expense(8808, "Cleaning")]
        )
        by_name = {u.expense_name: u.id for u in updates}

        assert by_name["Insurance HOI"] is None

    def test_rows_with_no_new_figure_are_dropped(self):
        # Nothing to apply, and emitting a null would blank a number the analyst
        # can see.
        options = [
            option
            for option in _options(opex_by_size=None, purchase_price=None)
            if option.keyed_on is OpexKeyedOn.BEDROOMS
        ]

        updates = opex_catalog.resolve_opex_updates(options, [])

        assert "Property Taxes (Monthly)" not in {u.expense_name for u in updates}

    def test_an_empty_ledger_yields_all_inserts(self):
        updates = opex_catalog.resolve_opex_updates(self._bedroom_keyed(), [])

        assert updates
        assert all(update.id is None for update in updates)

    def test_none_ledger_is_tolerated(self):
        assert opex_catalog.resolve_opex_updates(self._bedroom_keyed(), None)

    def test_the_first_of_two_rows_sharing_a_label_wins(self):
        # Nothing stops an analyst adding a row that duplicates a seeded label;
        # the earlier row is the seeded one.
        ledger = [self._expense(1, "Cleaning"), self._expense(2, "Cleaning")]

        updates = opex_catalog.resolve_opex_updates(self._bedroom_keyed(), ledger)

        assert next(u for u in updates if u.expense_name == "Cleaning").id == 1

    def test_amounts_are_the_catalogs_not_the_ledgers(self):
        ledger = [self._expense(8808, "Cleaning")]  # monthly_amount 1

        updates = opex_catalog.resolve_opex_updates(self._bedroom_keyed(), ledger)

        cleaning = next(u for u in updates if u.expense_name == "Cleaning")
        assert cleaning.monthly_amount == Decimal("1462.5")


class TestBuildOpexPropertyTaxes:
    """Amounts are money, so they are stored at cents.

    The assertions compare ``str(...)`` rather than the Decimal itself:
    Decimal equality ignores scale (Decimal("6000.0000") == Decimal("6000.00")),
    so only the string pins the number of decimal places actually persisted.
    """

    def test_amounts_are_quantized_to_cents(self):
        # 0.0125 carries four decimal places of its own, which would otherwise
        # propagate into the stored blob as 6000.0000.
        result = opex_catalog.build_opex_property_taxes(
            property_tax_pct=Decimal("0.0125"),
            purchase_price=Decimal("480000"),
        )

        assert str(result["annual_amount"]) == "6000.00"
        assert str(result["monthly_amount"]) == "500.00"

    def test_a_repeating_monthly_amount_is_rounded(self):
        result = opex_catalog.build_opex_property_taxes(
            property_tax_pct=Decimal("0.0125"),
            purchase_price=Decimal("500000"),
        )

        # 6250 / 12 = 520.8333...
        assert str(result["annual_amount"]) == "6250.00"
        assert str(result["monthly_amount"]) == "520.83"

    def test_rounding_is_half_even_matching_the_calculator(self):
        # 375000 * 0.0133 = 4987.50, / 12 = 415.625 exactly. Half-even gives
        # 415.62, half-up would give 415.63. This follows
        # UnderwritingCalculator._money so every money figure on the payload
        # rounds the same way.
        result = opex_catalog.build_opex_property_taxes(
            property_tax_pct=Decimal("0.0133"),
            purchase_price=Decimal("375000"),
        )

        assert str(result["annual_amount"]) == "4987.50"
        assert str(result["monthly_amount"]) == "415.62"

    def test_inputs_keep_the_unrounded_figures(self):
        result = opex_catalog.build_opex_property_taxes(
            property_tax_pct=Decimal("0.0125"),
            purchase_price=Decimal("480000"),
        )

        assert result["source"] == "opex_property_tax_pct"
        assert result["inputs"] == {
            "opex_property_tax_pct": Decimal("0.0125"),
            "purchase_price": Decimal("480000"),
        }

    def test_the_zillow_annual_source_is_quantized_too(self):
        result = opex_catalog.build_opex_property_taxes(
            property_tax_pct=None,
            purchase_price=None,
            zillow_annual_tax=Decimal("7231.4567"),
        )

        assert result["source"] == "zillow_annual_tax"
        assert str(result["annual_amount"]) == "7231.46"
        # 7231.4567 / 12 = 602.6213916...
        assert str(result["monthly_amount"]) == "602.62"

    def test_returns_none_when_no_source_resolves(self):
        assert (
            opex_catalog.build_opex_property_taxes(
                property_tax_pct=None, purchase_price=Decimal("480000")
            )
            is None
        )
        assert (
            opex_catalog.build_opex_property_taxes(
                property_tax_pct=Decimal("0.0125"), purchase_price=None
            )
            is None
        )
