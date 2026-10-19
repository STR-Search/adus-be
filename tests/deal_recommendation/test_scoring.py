from decimal import Decimal

import pytest

from app.deal_recommendation.services.scoring import (
    deal_metrics,
    score_deals,
    similar_deals,
)
from tests.deal_recommendation.factories import make_deal


def test_metrics_computes_ratios():
    deal = make_deal(
        1,
        tax_savings=Decimal("155000"),
        total_oop=Decimal("212000"),
        mid_gross_revenue=Decimal("120000"),
        purchase_price=Decimal("1000000"),
    )
    metrics = deal_metrics(deal)
    assert metrics["tax_return_on_capital"] == pytest.approx(0.7311, abs=1e-4)
    assert metrics["one_pct_ratio"] == pytest.approx(0.01)
    assert metrics["y1_coc_incl_tax_savings"] == pytest.approx(0.40)


def _pair():
    a = make_deal(1, tax_savings=Decimal("150000"), m_cash_on_cash=Decimal("0.02"))
    b = make_deal(2, tax_savings=Decimal("50000"), m_cash_on_cash=Decimal("0.15"))
    return [a, b]


def test_higher_weighted_metric_ranks_first():
    ranked = score_deals(_pair(), weights={"tax_savings": 5, "m_cash_on_cash": 1})
    assert [s.deal.id for s in ranked] == [1, 2]
    ranked = score_deals(_pair(), weights={"tax_savings": 1, "m_cash_on_cash": 5})
    assert [s.deal.id for s in ranked] == [2, 1]


def test_missing_metric_scores_25th_percentile_and_is_listed():
    deals = [
        make_deal(1, tax_savings=Decimal("100000")),
        make_deal(2, tax_savings=Decimal("50000")),
        make_deal(3, tax_savings=None),
    ]
    ranked = {s.deal.id: s for s in score_deals(deals, weights={"tax_savings": 5})}
    assert ranked[3].missing == ["tax_savings"]
    assert ranked[3].breakdown["tax_savings"] == pytest.approx(100 * 5 * 0.25 / 5)
    assert ranked[1].missing == []
    assert ranked[1].score == 100.0


def test_unweighted_missing_metric_is_not_listed():
    ranked = score_deals([make_deal(1, tax_savings=None)], weights={"m_cash_on_cash": 2})
    assert ranked[0].missing == []


def test_total_oop_lower_is_better():
    deals = [make_deal(1, total_oop=Decimal("300000")), make_deal(2, total_oop=Decimal("100000"))]
    assert score_deals(deals, weights={"total_oop": 3})[0].deal.id == 2


def test_state_preference_adds_bonus():
    deals = [make_deal(1, state="GA"), make_deal(2, state="fl")]
    ranked = score_deals(deals, weights={"tax_savings": 1}, state_preference={"FL": 2})
    assert ranked[0].deal.id == 2
    assert ranked[0].breakdown["state_preference"] > 0


def test_tag_preference_and_text_boost():
    deals = [make_deal(1), make_deal(2, boolean_tags={"turnkey": True}), make_deal(3)]
    ranked = score_deals(
        deals,
        weights={},
        tag_preferences={"turnkey": 2},
        text_boost_ids={3},
        text_boost_weight=3,
    )
    assert [s.deal.id for s in ranked] == [3, 2, 1]


def test_scores_are_bounded_0_100():
    deals = [make_deal(i, tax_savings=Decimal(i * 10000)) for i in range(1, 6)]
    for scored in score_deals(deals, weights={"tax_savings": 5}, state_preference={"FL": 2}):
        assert 0 <= scored.score <= 100


def test_no_weights_gives_zero_scores():
    assert all(s.score == 0 for s in score_deals(_pair(), weights={}))


def test_ties_break_on_id():
    deals = [make_deal(9), make_deal(4)]
    assert [s.deal.id for s in score_deals(deals, weights={"tax_savings": 1})] == [4, 9]


def test_similar_deals_prefers_closest_anchor_and_same_state():
    deals = [
        make_deal(1, state="GA", total_oop=Decimal("210000"), tax_savings=Decimal("147000")),
        make_deal(2, state="FL", total_oop=Decimal("400000"), tax_savings=Decimal("40000")),
        make_deal(3, state="FL", total_oop=Decimal("90000"), tax_savings=Decimal("30000")),
    ]
    ranked = similar_deals(
        deals,
        anchors=[{"total_oop": 212000, "tax_return_on_capital": 0.73}],
        anchor_states={"GA"},
    )
    assert ranked[0].deal.id == 1
    assert ranked[0].breakdown["state_match"] > 0
    assert all(0 <= s.score <= 100 for s in ranked)


def test_empty_pool_returns_empty_list():
    assert score_deals([], weights={"tax_savings": 5}) == []
    assert similar_deals([], anchors=[{"total_oop": 1}], anchor_states=set()) == []
