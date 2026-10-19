import pytest

from app.deal_recommendation.services.pool import dedupe_by_address, normalize_address
from tests.deal_recommendation.factories import approved, make_deal


@pytest.mark.parametrize(
    "a, b",
    [
        ("12664 115th St, Largo, FL 33778 | MLS #TB8509860 | Zillow", "12664 115th St, Largo, FL 33778"),
        ("(4BD) 6431 S Lagoon Dr, Panama City Beach, FL 32408", "(5BD) 6431 S Lagoon Dr, Panama City Beach, FL 32408"),
        ("1004 SW 19 Street, Fort Lauderdale, FL 33315", "1004 sw 19 st, fort lauderdale, fl 33315"),
        ("674 Glasco Turnpike, Saugerties, NY 12477", "674 Glasco Tpke, Saugerties, NY"),
        ("Off Market 5 bed: Broken Bow", "Off Market 5 bed: Broken Bow"),
    ],
)
def test_same_property_normalizes_equal(a, b):
    assert normalize_address(a, None, None, None) == normalize_address(b, None, None, None)


def test_different_properties_stay_different():
    assert normalize_address("1 Vista Ridge Dr, Galena, IL 61036", None, None, None) != (
        normalize_address("Vista Ridge Dr, East Jewett, NY", None, None, None)
    )


def test_missing_address_falls_back_to_street_city_state():
    assert normalize_address(None, "12 Oak Lane", "Largo", "FL") == normalize_address(
        "12 Oak Ln, Largo, FL", None, None, None
    )


def test_dedupe_keeps_latest_approved():
    addr = "1 Vista Ridge Dr, Galena, IL 61036"
    deals = [
        make_deal(818, property_address=addr, deal_approved=approved(2026, 3, 11)),
        make_deal(1060, property_address=addr, deal_approved=approved(2026, 4, 22)),
        make_deal(5),
    ]
    assert [d.id for d in dedupe_by_address(deals)] == [1060, 5]


def test_dedupe_tie_breaks_on_highest_id():
    addr = "Off Market 5 bed: Broken Bow"
    deals = [make_deal(1703, property_address=addr), make_deal(1736, property_address=addr)]
    assert [d.id for d in dedupe_by_address(deals)] == [1736]
