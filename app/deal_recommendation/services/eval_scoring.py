"""Score an agent run against the deals the team actually sent a client.

Hits are matched by normalized address, not id: the same property is often
several underwriting rows, and the pool keeps only one of them.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.deal_recommendation.services.pool import deal_address_key, normalize_address
from app.iron_bank.services.deal_catalog_service import CatalogDeal

TOP_N = 20


@dataclass
class CaseScore:
    case: str
    pool_size: int
    sent_in_pool: int
    shortlist_hits: int
    shortlist_size: int
    top20_hits: int
    random_top20: float
    random_shortlist: float


def score_case(
    *,
    case_name: str,
    sent_addresses: Sequence[str],
    pool: Sequence[CatalogDeal],
    shortlist_ids: Sequence[int],
    last_search_ids: Sequence[int],
) -> CaseScore:
    key_by_id = {deal.id: deal_address_key(deal) for deal in pool}
    pool_keys = set(key_by_id.values())
    sent_keys = {normalize_address(a, None, None, None) for a in sent_addresses} & pool_keys
    pool_size = len(pool_keys)

    def hits(ids: Sequence[int]) -> int:
        return len({key_by_id[i] for i in ids if i in key_by_id} & sent_keys)

    def random_hits(k: int) -> float:
        return min(k, pool_size) * len(sent_keys) / pool_size if pool_size else 0.0

    return CaseScore(
        case=case_name,
        pool_size=pool_size,
        sent_in_pool=len(sent_keys),
        shortlist_hits=hits(shortlist_ids),
        shortlist_size=len(shortlist_ids),
        top20_hits=hits(list(last_search_ids)[:TOP_N]),
        random_top20=round(random_hits(TOP_N), 2),
        random_shortlist=round(random_hits(len(shortlist_ids)), 2),
    )
