"""Deterministic deal scoring — the agent chooses weights, this code ranks.

Every metric is turned into a percentile within the candidate pool, so a weight
means the same thing whatever the metric's units. The agent never computes or
ranks numbers itself; it reads the score and its per-component breakdown.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.iron_bank.services.deal_catalog_service import CatalogDeal

METRICS: tuple[str, ...] = (
    "tax_savings",
    "tax_return_on_capital",
    "m_cash_on_cash",
    "y1_coc_incl_tax_savings",
    "one_pct_ratio",
    "purchase_price",
    "total_oop",
)
LOWER_IS_BETTER: frozenset[str] = frozenset({"total_oop"})
MISSING_PERCENTILE = 0.25
SIMILARITY_FEATURES = (
    "purchase_price",
    "total_oop",
    "bedrooms",
    "tax_return_on_capital",
    "m_cash_on_cash",
    "one_pct_ratio",
)
_STATE_MATCH_BONUS = 0.1


@dataclass
class ScoredDeal:
    deal: CatalogDeal
    metrics: dict[str, float | None]
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)


def _f(value) -> float | None:
    return None if value is None else float(value)


def deal_metrics(deal: CatalogDeal) -> dict[str, float | None]:
    tax, oop = _f(deal.tax_savings), _f(deal.total_oop)
    revenue, price = _f(deal.mid_gross_revenue), _f(deal.purchase_price)
    return {
        "tax_savings": tax,
        "tax_return_on_capital": tax / oop if tax is not None and oop else None,
        "m_cash_on_cash": _f(deal.m_cash_on_cash),
        "y1_coc_incl_tax_savings": _f(deal.y1_coc_incl_tax_savings_mid),
        "one_pct_ratio": revenue / 12 / price if revenue is not None and price else None,
        "purchase_price": price,
        "total_oop": oop,
        "bedrooms": _f(deal.bedrooms),
    }


def _percentile(value: float, values: Sequence[float]) -> float:
    """Share of the pool's values strictly below ``value``, clamped to 0..1."""
    if len(values) <= 1:
        return 0.5
    below = sum(1 for v in values if v < value)
    return min(1.0, below / (len(values) - 1))


def _pool_values(all_metrics: Sequence[dict], name: str) -> list[float]:
    return [m[name] for m in all_metrics if m[name] is not None]


def score_deals(
    deals: Sequence[CatalogDeal],
    *,
    weights: Mapping[str, int],
    state_preference: Mapping[str, int] | None = None,
    tag_preferences: Mapping[str, int] | None = None,
    text_boost_ids: set[int] | None = None,
    text_boost_weight: int = 0,
) -> list[ScoredDeal]:
    weights = {k: w for k, w in weights.items() if k in METRICS and w > 0}
    states = {s.upper(): w for s, w in (state_preference or {}).items() if w > 0}
    tags = {t: w for t, w in (tag_preferences or {}).items() if w > 0}
    boost_ids = text_boost_ids or set()
    boost = text_boost_weight if boost_ids else 0

    maximum = sum(weights.values()) + max(states.values(), default=0)
    maximum += sum(tags.values()) + boost
    scale = 100 / maximum if maximum else 0.0

    all_metrics = [deal_metrics(deal) for deal in deals]
    pool = {name: _pool_values(all_metrics, name) for name in weights}

    scored = []
    for deal, metrics in zip(deals, all_metrics):
        breakdown, missing = {}, []
        for name, weight in weights.items():
            value = metrics[name]
            if value is None:
                pct = MISSING_PERCENTILE
                missing.append(name)
            else:
                pct = _percentile(value, pool[name])
                if name in LOWER_IS_BETTER:
                    pct = 1 - pct
            breakdown[name] = weight * pct * scale
        if states:
            breakdown["state_preference"] = states.get((deal.state or "").upper(), 0) * scale
        for tag, weight in tags.items():
            breakdown[f"tag:{tag}"] = weight * scale if deal.boolean_tags.get(tag) else 0.0
        if boost:
            breakdown["text_match"] = boost * scale if deal.id in boost_ids else 0.0
        scored.append(
            ScoredDeal(
                deal=deal,
                metrics=metrics,
                score=round(sum(breakdown.values()), 1),
                breakdown={k: round(v, 1) for k, v in breakdown.items()},
                missing=missing,
            )
        )
    scored.sort(key=lambda s: (-s.score, s.deal.id))
    return scored


def similar_deals(
    deals: Sequence[CatalogDeal],
    *,
    anchors: Sequence[Mapping[str, float]],
    anchor_states: set[str],
) -> list[ScoredDeal]:
    """Rank deals by closeness to the closest anchor (a deal the client liked)."""
    all_metrics = [deal_metrics(deal) for deal in deals]
    pool = {name: _pool_values(all_metrics, name) for name in SIMILARITY_FEATURES}
    states = {s.upper() for s in anchor_states}
    anchor_pcts = [
        {
            name: _percentile(float(anchor[name]), pool[name])
            for name in SIMILARITY_FEATURES
            if anchor.get(name) is not None and pool[name]
        }
        for anchor in anchors
    ]

    scored = []
    for deal, metrics in zip(deals, all_metrics):
        distances = []
        for anchor in anchor_pcts:
            diffs = [
                abs(_percentile(metrics[name], pool[name]) - pct)
                for name, pct in anchor.items()
                if metrics[name] is not None
            ]
            if diffs:
                distances.append(sum(diffs) / len(diffs))
        distance = min(distances, default=1.0)
        state_match = _STATE_MATCH_BONUS if (deal.state or "").upper() in states else 0.0
        scale = 100 / (1 + _STATE_MATCH_BONUS)
        scored.append(
            ScoredDeal(
                deal=deal,
                metrics=metrics,
                score=round((1 - distance + state_match) * scale, 1),
                breakdown={
                    "distance": round(distance, 3),
                    "state_match": round(state_match * scale, 1),
                },
            )
        )
    scored.sort(key=lambda s: (-s.score, s.deal.id))
    return scored
