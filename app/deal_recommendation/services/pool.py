"""Candidate-pool hygiene: one deal per physical property.

The same property is often underwritten more than once as separate rows (not
versions of one series), with different numbers — e.g. a 4BD and a 5BD
scenario, or a legacy-sheet row plus a newer adus row. Recommending two of them
would show the client the same house twice, so the pool keeps one per address.
"""

import re
from collections.abc import Sequence
from datetime import datetime, timezone

from app.iron_bank.services.deal_catalog_service import CatalogDeal

_SUFFIXES = {
    "street": "st",
    "road": "rd",
    "drive": "dr",
    "lane": "ln",
    "avenue": "ave",
    "court": "ct",
    "terrace": "ter",
    "trail": "trl",
    "turnpike": "tpke",
}
_LEADING_PARENS = re.compile(r"^\s*\([^)]*\)\s*")
_ZIP = re.compile(r"\b\d{5}(-\d{4})?\b")
_PUNCTUATION = re.compile(r"[^\w\s]")
_OLDEST = datetime.min.replace(tzinfo=timezone.utc)


def normalize_address(
    property_address: str | None,
    street: str | None,
    city: str | None,
    state: str | None,
) -> str:
    raw = property_address or " ".join(p for p in (street, city, state) if p)
    text = raw.lower().split("|", 1)[0]
    text = _LEADING_PARENS.sub("", text)
    text = _ZIP.sub(" ", text)
    text = _PUNCTUATION.sub(" ", text)
    return " ".join(_SUFFIXES.get(token, token) for token in text.split())


def deal_address_key(deal: CatalogDeal) -> str:
    return normalize_address(deal.property_address, deal.street, deal.city, deal.state)


def _recency(deal: CatalogDeal) -> tuple[datetime, int]:
    approved = deal.deal_approved
    if approved is not None and approved.tzinfo is None:
        approved = approved.replace(tzinfo=timezone.utc)
    return (approved or _OLDEST, deal.id)


def dedupe_by_address(deals: Sequence[CatalogDeal]) -> list[CatalogDeal]:
    """Keep the latest-approved deal per address (then the highest id).

    Kept deals stay in their input order.
    """
    best: dict[str, CatalogDeal] = {}
    for deal in deals:
        key = deal_address_key(deal)
        current = best.get(key)
        if current is None or _recency(deal) > _recency(current):
            best[key] = deal
    kept = {deal.id for deal in best.values()}
    return [deal for deal in deals if deal.id in kept]
