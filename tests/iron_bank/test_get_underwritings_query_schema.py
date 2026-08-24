from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.iron_bank.enums import UnderwritingSortBy
from app.iron_bank.models.underwriting import Underwriting
from app.iron_bank.schemas.get_underwriting import GetUnderwritingsQuery


@pytest.mark.parametrize("scenario", ["m", "h"])
def test_cash_on_cash_bounds_accept_min_below_max(scenario):
    query = GetUnderwritingsQuery(
        **{
            f"min_{scenario}_cash_on_cash": Decimal("0.1"),
            f"max_{scenario}_cash_on_cash": Decimal("0.4"),
        }
    )

    assert getattr(query, f"min_{scenario}_cash_on_cash") == Decimal("0.1")
    assert getattr(query, f"max_{scenario}_cash_on_cash") == Decimal("0.4")


@pytest.mark.parametrize("scenario", ["m", "h"])
def test_cash_on_cash_bounds_accept_equal_min_and_max(scenario):
    """Both ends inclusive, matching the other range filters."""
    query = GetUnderwritingsQuery(
        **{
            f"min_{scenario}_cash_on_cash": Decimal("0.25"),
            f"max_{scenario}_cash_on_cash": Decimal("0.25"),
        }
    )

    assert getattr(query, f"max_{scenario}_cash_on_cash") == Decimal("0.25")


@pytest.mark.parametrize("scenario", ["m", "h"])
def test_cash_on_cash_bounds_reject_inverted_range(scenario):
    with pytest.raises(ValidationError) as excinfo:
        GetUnderwritingsQuery(
            **{
                f"min_{scenario}_cash_on_cash": Decimal("0.9"),
                f"max_{scenario}_cash_on_cash": Decimal("0.2"),
            }
        )

    assert (
        f"min_{scenario}_cash_on_cash must be less than or equal to "
        f"max_{scenario}_cash_on_cash"
    ) in str(excinfo.value)


@pytest.mark.parametrize("scenario", ["m", "h"])
def test_cash_on_cash_bounds_are_independent_of_each_other(scenario):
    """One end alone is a valid open-ended bound."""
    query = GetUnderwritingsQuery(
        **{f"min_{scenario}_cash_on_cash": Decimal("0.9")}
    )

    assert getattr(query, f"min_{scenario}_cash_on_cash") == Decimal("0.9")
    assert getattr(query, f"max_{scenario}_cash_on_cash") is None


@pytest.mark.parametrize(
    "value, expected",
    [
        ("m_cash_on_cash", UnderwritingSortBy.M_CASH_ON_CASH),
        ("h_cash_on_cash", UnderwritingSortBy.H_CASH_ON_CASH),
    ],
)
def test_sort_by_accepts_mid_and_high_cash_on_cash(value, expected):
    assert GetUnderwritingsQuery(sort_by=value).sort_by is expected


@pytest.mark.parametrize("sort_by", list(UnderwritingSortBy))
def test_every_sort_by_value_is_a_real_underwriting_column(sort_by):
    """The repository sorts with getattr, so a bad value fails at request time."""
    assert hasattr(Underwriting, sort_by.value)
