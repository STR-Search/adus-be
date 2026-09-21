"""The CSV-side contract of the opex updater.

Everything here is pure: parsing, validation and diffing run with no session,
so the rules that decide what gets written are testable without a database.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from scripts.seeding_scripts import update_opex_from_csv as updater

BEDROOMS = updater.SPECS["bedrooms"]


def _cell(raw, column="cleaning_fee"):
    return updater.parse_cell(
        raw,
        column=column,
        is_percent=column in BEDROOMS.percent_columns,
        where="test.csv line 2",
    )


def _write(tmp_path, body, name="opex.csv"):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


HEADER = "market_name,bedrooms,property_taxes,cleaning_fee,pool_and_hot_tub"


class TestPercentColumns:
    """Stored as fractions, written as percentages — the 100x hazard."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1.00%", "0.01"),
            ("16.00%", "0.16"),
            ("4.25%", "0.0425"),
            ("0.06%", "0.0006"),
            ("3.50%", "0.035"),
        ],
    )
    def test_a_percentage_becomes_a_fraction_at_minimal_scale(self, raw, expected):
        # str(), not ==: Decimal equality ignores scale, and scale is visible on
        # the wire because PlainDecimal formats with "f". 1.00% / 100 is
        # 0.0100, and the stored figures are 0.01.
        assert str(_cell(raw, "property_taxes")) == expected

    def test_a_percent_column_without_a_percent_sign_is_refused(self):
        # A bare "1.00" here would store 100%, not 1%. Guessing is worse than
        # stopping, so this aborts the whole run rather than the row.
        with pytest.raises(updater.CsvError, match="has no '%'"):
            _cell("1.00", "property_taxes")

    def test_a_percent_sign_in_a_plain_amount_column_is_refused(self):
        # Catches a reordered or renamed header, which would otherwise write
        # every column one position off.
        with pytest.raises(updater.CsvError, match="stored as a plain amount"):
            _cell("125%", "cleaning_fee")


class TestPlainAmounts:
    def test_currency_decoration_is_stripped(self):
        assert _cell("$18,225") == Decimal("18225")

    def test_a_whole_number_never_comes_back_in_exponent_form(self):
        # Decimal.normalize() renders 350 as 3.5E+2, which would persist as
        # "3.5E+2" through a plain string format.
        assert str(_cell("350")) == "350"

    def test_a_fractional_amount_keeps_its_significant_digits(self):
        assert str(_cell("8.5", "num_of_turns")) == "8.5"

    def test_a_non_number_is_refused(self):
        with pytest.raises(updater.CsvError, match="is not a number"):
            _cell("n0ne")


class TestNullAndBlank:
    """The two are deliberately different."""

    @pytest.mark.parametrize("raw", ["null", "NULL", "None", "n/a"])
    def test_the_null_sentinel_clears_the_column(self, raw):
        assert _cell(raw, "land_value") is None

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_an_empty_cell_leaves_the_column_alone(self, raw):
        # A CSV exported with holes in it must not blank out stored data.
        assert _cell(raw, "land_value") is updater.LEAVE_UNCHANGED


class TestLoadCsv:
    def test_a_good_file_parses_into_rows(self, tmp_path):
        path = _write(tmp_path, f"{HEADER}\nAlbrightsville - PA,4,1.00%,225,350\n")

        rows, columns = updater.load_csv(BEDROOMS, path)

        assert columns == ["pool_and_hot_tub", "cleaning_fee", "property_taxes"]
        assert rows[0]["market_name"] == "Albrightsville - PA"
        assert rows[0]["key_value"] == 4
        assert rows[0]["values"]["property_taxes"] == Decimal("0.01")

    def test_an_unrecognised_column_is_refused(self, tmp_path):
        path = _write(tmp_path, "market_name,bedrooms,pool_hot_tub_lo\nA,1,125\n")

        with pytest.raises(updater.CsvError, match="unrecognised column"):
            updater.load_csv(BEDROOMS, path)

    def test_a_duplicate_key_is_refused(self, tmp_path):
        # Which row wins would be undefined, so the file is wrong, not the run.
        path = _write(tmp_path, f"{HEADER}\nA,1,1.00%,125,350\nA,1,1.00%,130,350\n")

        with pytest.raises(updater.CsvError, match="duplicate"):
            updater.load_csv(BEDROOMS, path)

    def test_a_missing_key_column_is_refused(self, tmp_path):
        path = _write(tmp_path, "market_name,cleaning_fee\nA,125\n")

        with pytest.raises(updater.CsvError, match="'bedrooms' is missing"):
            updater.load_csv(BEDROOMS, path)

    def test_a_non_integer_key_is_refused(self, tmp_path):
        path = _write(tmp_path, f"{HEADER}\nA,four,1.00%,125,350\n")

        with pytest.raises(updater.CsvError, match="not an integer"):
            updater.load_csv(BEDROOMS, path)

    def test_columns_absent_from_the_csv_are_simply_not_updated(self, tmp_path):
        # A partial CSV is legitimate — it updates the columns it carries.
        path = _write(tmp_path, "market_name,bedrooms,cleaning_fee\nA,1,225\n")

        _, columns = updater.load_csv(BEDROOMS, path)

        assert columns == ["cleaning_fee"]


class TestResolveMarketIds:
    def _markets(self):
        return [
            SimpleNamespace(id=1, market_name="Albrightsville - PA"),
            SimpleNamespace(id=2, market_name="Asheville - NC"),
        ]

    def _row(self, name, csv_market_id=""):
        return {
            "market_name": name,
            "key_value": 1,
            "csv_market_id": csv_market_id,
            "where": "test.csv line 2",
        }

    def test_the_id_comes_from_the_name(self):
        rows = [self._row("Asheville - NC")]

        assert updater.resolve_market_ids(rows, self._markets()) == set()
        assert rows[0]["market_id"] == 2

    def test_an_unknown_name_is_reported_not_raised(self):
        # Row-level: the rest of the file still applies.
        rows = [self._row("Nowhere - ZZ")]

        assert updater.resolve_market_ids(rows, self._markets()) == {"Nowhere - ZZ"}
        assert rows[0]["market_id"] is None

    def test_a_stale_csv_market_id_aborts_the_run(self):
        # The CSV's own id is a checksum on the export, not an input. Preferring
        # either side silently would write the wrong market's opex.
        rows = [self._row("Asheville - NC", csv_market_id="99")]

        with pytest.raises(updater.CsvError, match="disagrees with market_keys_master"):
            updater.resolve_market_ids(rows, self._markets())

    def test_a_matching_csv_market_id_passes(self):
        rows = [self._row("Asheville - NC", csv_market_id="2")]

        assert updater.resolve_market_ids(rows, self._markets()) == set()


class TestDiffRow:
    def _record(self, **values):
        return SimpleNamespace(**values)

    def test_only_genuine_changes_are_reported(self):
        record = self._record(cleaning_fee=Decimal("225"), software=Decimal("0"))

        changes = updater.diff_row(
            record, {"cleaning_fee": Decimal("250"), "software": Decimal("0")}
        )

        assert changes == {"cleaning_fee": (Decimal("225"), Decimal("250"))}

    def test_a_scale_only_difference_is_not_a_change(self):
        # 125.00 and 125 are the same figure; rewriting one as the other would
        # churn the stored scale, which is visible on the wire, for nothing.
        record = self._record(cleaning_fee=Decimal("125.00"))

        assert updater.diff_row(record, {"cleaning_fee": Decimal("125")}) == {}

    def test_a_blank_cell_is_never_a_change(self):
        record = self._record(land_value=Decimal("0.16"))

        assert updater.diff_row(record, {"land_value": updater.LEAVE_UNCHANGED}) == {}

    def test_null_over_null_is_not_a_change(self):
        record = self._record(land_value=None)

        assert updater.diff_row(record, {"land_value": None}) == {}

    def test_a_value_can_be_cleared_to_null(self):
        record = self._record(land_value=Decimal("0.16"))

        assert updater.diff_row(record, {"land_value": None}) == {
            "land_value": (Decimal("0.16"), None)
        }

    def test_filling_a_null_is_a_change(self):
        # The pool_and_hot_tub case: a new column, null everywhere.
        record = self._record(pool_and_hot_tub=None)

        assert updater.diff_row(record, {"pool_and_hot_tub": Decimal("350")}) == {
            "pool_and_hot_tub": (None, Decimal("350"))
        }


class TestSpecs:
    def test_value_columns_are_read_off_the_model(self):
        # So a column added to the table is updatable without touching this
        # script — the whole reason it introspects rather than listing columns.
        assert "pool_and_hot_tub" in BEDROOMS.value_columns
        assert not {"id", "market_id", "deleted_at", "bedrooms"} & set(
            BEDROOMS.value_columns
        )

    def test_the_size_table_is_wired_the_same_way(self):
        size = updater.SPECS["size"]

        assert size.key_column == "sqft"
        assert size.value_columns == ["internet", "pest_control", "utilities"]
        assert size.percent_columns == frozenset()
