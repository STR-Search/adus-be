from decimal import Decimal

import pytest

from scripts import backfill_legacy_underwritings as backfill


def _pad(row: tuple, width: int = 13) -> tuple:
    return row + (None,) * (width - len(row))


# Mimics the current (v4, link 1558+) template: construction loan block,
# cleaning cost block, analyst notes, taxes, comp set.
NEW_FORMAT_GRID = [
    _pad((None, None, None, None, "Prepared By:", "Taylor J", None, None, None, None, "Analyst Notes")),
    _pad((None, None, None, None, "PROPERTY URL:", "https://www.zillow.com/homedetails/1", None, None, None, None, "Solid bones")),
    _pad((None, None, None, None, "Optimization List (Estimate)", None, None, "Operating Expenses (OPEX)", "Monthly")),
    _pad((None, None, None, None, "Furniture / Decor", 80000, None, "Internet", 100)),
    _pad((None, None, None, None, "Hot Tub", 14000, None, "Cleaning", 1500, None, "Cleaning Cost", "# of Turns")),
    _pad((None, "Purchase Details", None, "$", None, None, None, "Other", None, None, 300, 5)),
    _pad((None, "Purchase Price", None, 1000000, None, None, None, "Total Operating Expenses", 1600)),
    _pad((None, "Down Payment", 0.1, 100000, "Total Optimization Range", 94000)),
    _pad((None, "Interest Rate", None, 0.065, None, None, None, None, None, None, "Loan Amount", "Int Rate (Annual)", "Term (Years)")),
    _pad((None, "Mortgage Years", None, 30, None, None, None, None, None, None, 50000, 0.065, 7)),
    _pad((None, "Closing Costs", 0.03, 30000)),
    _pad((None, "Taxes",)),
    _pad((None, "Land Assumptions", 0.3)),
    _pad((None, "Tax Savings", 120645.9)),
    _pad((None, "Forecasted Revenue ", None, 170000, 182000, 195000)),
    _pad((None, "Operating Expenses (Annual Estimated)", None, 67795, 70620, 73444)),
    _pad((None, "Co-hosting Fee", 0.1, 17000, 18200, 19500)),
    _pad((None, "Net Operating Income", None, 102204, 111380, 121555)),
    _pad((None, None, None, "Year 1 Cash on Cash, including Tax Savings")),
    _pad((None, None, None, "Low", "Mid", "High")),
    _pad((None, None, None, 0.43, 0.47, 0.52)),
    _pad((None, None, None, None, None, None, None, "Comp Set")),
    _pad((None, None, None, None, None, None, None, "Listing URL", "Revenue", "Bedrooms", "Sleeps")),
    _pad((None, None, None, None, None, None, None, "https://airbnb.com/rooms/1", 225875, 5, 12)),
]

# Mimics the oldest template: 'Optimzation' typo, no construction loan or
# cleaning-cost block, totals labelled just 'Total'.
OLD_FORMAT_GRID = [
    _pad((None, None, None, None, "Prepared By:", "John B")),
    _pad((None, None, None, None, "PROPERTY URL:", "519 Jackson Keller, San Antonio, TX")),
    _pad((None, None, None, None, "Optimzation List (Rough Estimate)", None, None, "Operating Expenses (OPEX)", "Monthly")),
    _pad((None, None, None, None, "Pickleball Court", 35000, None, "Internet", 100)),
    _pad((None, "Purchase Details", None, "$", "Total", 35000, None, "Total Operating Expenses", 100)),
    _pad((None, "Purchase Price", None, 439000)),
    _pad((None, "Down Payment", 0.1, 43900)),
]


def test_parse_new_format_tab():
    tab = backfill.parse_deal_tab(NEW_FORMAT_GRID)

    assert tab["purchase_details"]["purchase_price"] == Decimal("1000000")
    assert tab["purchase_details"]["down_payment_pct"] == Decimal("0.1")
    assert tab["purchase_details"]["closing_costs"] == Decimal("30000")
    assert tab["purchase_details"]["construction_loan"] == {
        "loan_amount": Decimal("50000"),
        "interest_rate": Decimal("0.065"),
        "term_years": Decimal("7"),
    }
    assert tab["cleaning_cost"] == {
        "cleaning_cost": Decimal("300"),
        "turns_per_month": Decimal("5"),
    }
    assert tab["optimization_items"] == [
        {"category": "Furniture / Decor", "total_price": Decimal("80000")},
        {"category": "Hot Tub", "total_price": Decimal("14000")},
    ]
    # 'Other' has no amount and 'Total Operating Expenses' terminates the section
    assert tab["operating_expenses"] == [
        {"expense_name": "Internet", "monthly_amount": Decimal("100")},
        {"expense_name": "Cleaning", "monthly_amount": Decimal("1500")},
    ]
    assert tab["taxes"] == {
        "land_assumptions_pct": Decimal("0.3"),
        "tax_savings": Decimal("120645.9"),
    }
    assert tab["forecasted_revenue"] == {
        "co_hosting_fee_pct": Decimal("0.1"),
        "scenarios": {
            "low": {
                "forecasted_revenue": Decimal("170000"),
                "operating_expenses_annual": Decimal("67795"),
                "co_hosting_fee": Decimal("17000"),
                "net_operating_income": Decimal("102204"),
            },
            "mid": {
                "forecasted_revenue": Decimal("182000"),
                "operating_expenses_annual": Decimal("70620"),
                "co_hosting_fee": Decimal("18200"),
                "net_operating_income": Decimal("111380"),
            },
            "high": {
                "forecasted_revenue": Decimal("195000"),
                "operating_expenses_annual": Decimal("73444"),
                "co_hosting_fee": Decimal("19500"),
                "net_operating_income": Decimal("121555"),
            },
        },
    }
    assert tab["y1_coc_incl_tax_savings"] == {
        "low_pct": Decimal("0.43"),
        "mid_pct": Decimal("0.47"),
        "high_pct": Decimal("0.52"),
    }
    assert tab["comp_set"] == [
        {
            "listing_url": "https://airbnb.com/rooms/1",
            "revenue": Decimal("225875"),
            "bedrooms": 5,
            "sleeps": 12,
        }
    ]
    assert tab["analyst_notes"] == "Solid bones"
    assert tab["prepared_by"] == "Taylor J"
    assert tab["listing_url"] == "https://www.zillow.com/homedetails/1"
    assert tab["warnings"] == []


def test_parse_old_format_tab():
    tab = backfill.parse_deal_tab(OLD_FORMAT_GRID)

    assert tab["optimization_items"] == [
        {"category": "Pickleball Court", "total_price": Decimal("35000")}
    ]
    assert tab["operating_expenses"] == [
        {"expense_name": "Internet", "monthly_amount": Decimal("100")}
    ]
    assert tab["purchase_details"]["purchase_price"] == Decimal("439000")
    assert tab["purchase_details"].get("construction_loan") is None
    assert tab["cleaning_cost"] is None
    assert tab["taxes"] is None
    # a plain address in the PROPERTY URL cell is not a listing URL
    assert tab["listing_url"] is None
    assert tab["prepared_by"] == "John B"
    assert tab["warnings"] == []


def test_map_deal_status():
    assert backfill.map_deal_status("Present to Clients") == "present_to_clients"
    assert backfill.map_deal_status("Maybe (Save for Later)") == "maybe"

    assert (
        backfill.map_deal_status(None) == "Previously Underwritten - No Status"
    )

    assert (
        backfill.map_deal_status("Taylor Review Needed") == "analyst_completed"
    )
    assert (
        backfill.map_deal_status("Floorplan/ Video needed")
        == "awaiting_realtor_details"
    )


def test_map_deal_status_raises_for_unmapped_label():
    with pytest.raises(ValueError, match="unmapped sheet deal status"):
        backfill.map_deal_status("Some Brand New Sheet Status")


def test_build_deal_from_summary_row():
    summary = {
        "raw_status": "Present to Clients",
        "property_address": "909 Mango Isle, Fort Lauderdale, FL",
        "city": "Fort Lauderdale",
        "state": "FL",
        "analyst_name": "Taylor J",
        "approver_name": "John B",
        "purchase_price": 1875000.0,
        "total_oop": 562687.5,
        "prr": 0.1653,
        "low_gross_revenue": 280000,
        "mid_gross_revenue": 310000,
        "high_gross_revenue": 340000,
        "l_cash_on_cash": 0.0949,
        "m_cash_on_cash": 0.1413,
        "h_cash_on_cash": 0.1877,
        "deal_added": "2025-09-19 13:06:51",
        "deal_approved": "2025-09-21 09:30:00",
        "sleep_capacity": 12,
        "turnkey": "True",
        "property_pending": "False",
        "loom_vid": None,
        "notes": "RE Agent confirmed",
        "link": 1156,
    }

    deal = backfill.build_deal(1156, summary, None)
    uw = deal["underwriting"]

    assert uw["source"] == "legacy_sheet"
    assert uw["sheet_number"] == 1156
    assert uw["is_automated"] is False
    assert uw["deal_status"] == "present_to_clients"
    assert uw["purchase_price"] == Decimal("1875000.0")
    assert uw["total_oop"] == Decimal("562687.5")
    assert uw["street"] == "909 Mango Isle"
    assert uw["budget_to_pp"] == Decimal("562687.5") / Decimal("1875000.0")
    assert uw["turnkey"] is True
    assert uw["property_pending"] is False
    assert uw["deal_added"].year == 2025
    assert uw["deal_approved"].day == 21
    assert deal["analyst_name"] == "Taylor J"
    assert deal["approver_name"] == "John B"
    assert deal["notes"] == ["RE Agent confirmed"]
    assert "no deal tab in workbook (summary row only)" in deal["warnings"]


def test_build_deal_without_summary_defaults_to_no_status():
    deal = backfill.build_deal(42, None, backfill.parse_deal_tab(OLD_FORMAT_GRID))
    uw = deal["underwriting"]

    assert uw["deal_status"] == "Previously Underwritten - No Status"
    # purchase price falls back to the tab's Purchase Details
    assert uw["purchase_price"] == Decimal("439000")
    assert deal["analyst_name"] == "John B"  # from 'Prepared By:'
    assert "no summary row in any tracking tab (deal tab only)" in deal["warnings"]


def test_value_normalization():
    assert backfill.to_decimal("$1,234.50") == Decimal("1234.50")
    assert backfill.to_decimal("") is None
    assert backfill.to_decimal("n/a") is None
    assert backfill.to_int("5.0") == 5
    assert backfill.to_bool("True") is True
    assert backfill.to_bool(None) is False
    assert backfill.to_datetime("2025-09-19 13:06:51.11").tzinfo is not None


def test_user_matcher():
    class FakeUser:
        def __init__(self, id, first_name, last_name):
            self.id = id
            self.first_name = first_name
            self.last_name = last_name

    match = backfill.build_user_matcher(
        [FakeUser(1, "Taylor", "Johnson"), FakeUser(2, "John", "Baker")]
    )
    assert match("Taylor J") == 1
    assert match("taylor johnson") == 1
    assert match("John B") == 2
    assert match("Unknown Person") is None
    assert match(None) is None
