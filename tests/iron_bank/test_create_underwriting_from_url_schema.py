import pytest
from pydantic import ValidationError

from app.iron_bank.schemas.create_underwriting_from_url import (
    CreateUnderwritingFromUrlPayload,
)

URL = "https://www.zillow.com/homedetails/26110417_zpid/"


def test_market_id_zero_becomes_none():
    """0 is an unselected dropdown, not market 1.

    market_keys_master starts at id 1, so a literal 0 would load an empty
    context and then violate the FK on insert.
    """
    payload = CreateUnderwritingFromUrlPayload(url=URL, market_id=0)

    assert payload.market_id is None


def test_omitted_market_id_stays_none():
    assert CreateUnderwritingFromUrlPayload(url=URL).market_id is None


def test_explicit_null_market_id_stays_none():
    assert CreateUnderwritingFromUrlPayload(url=URL, market_id=None).market_id is None


@pytest.mark.parametrize("market_id", [1, 7, 42])
def test_real_market_ids_pass_through(market_id):
    payload = CreateUnderwritingFromUrlPayload(url=URL, market_id=market_id)

    assert payload.market_id == market_id


def test_url_is_still_required():
    with pytest.raises(ValidationError):
        CreateUnderwritingFromUrlPayload(market_id=3)
