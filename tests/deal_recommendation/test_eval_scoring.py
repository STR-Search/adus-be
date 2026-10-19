import pytest

from app.deal_recommendation.services.eval_scoring import score_case
from tests.deal_recommendation.factories import make_deal


def _pool(n):
    return [make_deal(i, property_address=f"{i} Pine St, Largo, FL 33770") for i in range(1, n + 1)]


def test_score_case_counts_hits_by_address_not_id():
    pool = _pool(10)
    score = score_case(
        case_name="c",
        sent_addresses=["3 Pine Street, Largo, FL", "4 Pine St, Largo, FL 33770"],
        pool=pool,
        shortlist_ids=[3, 7],
        last_search_ids=[4, 3, 9],
    )
    assert score.sent_in_pool == 2
    assert score.shortlist_hits == 1
    assert score.shortlist_size == 2
    assert score.top20_hits == 2


def test_hits_match_a_deduped_twin_with_a_different_id():
    pool = [make_deal(1060, property_address="1 Vista Ridge Dr, Galena, IL 61036")]
    score = score_case(
        case_name="c",
        sent_addresses=["1 Vista Ridge Dr, Galena, IL 61036"],
        pool=pool,
        shortlist_ids=[1060],
        last_search_ids=[],
    )
    assert score.shortlist_hits == 1


def test_random_baselines():
    pool = _pool(75)
    sent = [f"{i} Pine St, Largo, FL" for i in range(1, 14)]
    score = score_case(case_name="c", sent_addresses=sent, pool=pool,
                       shortlist_ids=[1, 2, 3, 4, 5], last_search_ids=[])
    assert score.random_top20 == pytest.approx(20 * 13 / 75, abs=0.01)
    assert score.random_shortlist == pytest.approx(5 * 13 / 75, abs=0.01)


def test_sent_addresses_missing_from_pool_reduce_sent_in_pool():
    score = score_case(case_name="c", sent_addresses=["1 Pine St, Largo, FL", "999 Nowhere Rd"],
                       pool=_pool(3), shortlist_ids=[], last_search_ids=[])
    assert score.sent_in_pool == 1
