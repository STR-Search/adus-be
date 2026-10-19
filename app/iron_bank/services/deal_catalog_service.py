"""Read-only deal catalog for the deal_recommendation domain.

This module is the single seam deal_recommendation is allowed to import from
iron_bank (see CLAUDE.md). It never writes, and it returns plain dataclasses,
never ORM objects. Financial numbers are recalculated through
``SimulateUnderwritingsService.simulate_row`` so the recommendation agent sees
the same math as the underwritings list's simulation mode; a row the calculator
cannot recalculate (many legacy-sheet rows) is kept only when its stored
financing already matches the requested terms, and dropped otherwise, so it is
never shown with numbers at the wrong terms.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.iron_bank.enums import DealStatus
from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.schemas.underwriting import (
    BOOLEAN_TAG_FIELDS,
    MULTI_SELECT_TAG_FIELDS,
    SINGLE_SELECT_TAG_FIELDS,
)
from app.iron_bank.services.simulate_underwritings_service import (
    SimulateUnderwritingsService,
)
from app.iron_bank.services.underwriting_calculator import UnderwritingCalculator

COMP_AMENITY_FIELDS = (
    "has_pool",
    "has_hot_tub",
    "has_sauna",
    "has_mini_golf",
    "has_game_room",
    "has_pickleball",
    "has_movie_theater",
    "has_playground",
    "has_waterfront",
)


@dataclass(frozen=True)
class CatalogDeal:
    id: int
    property_address: str | None
    street: str | None
    city: str | None
    state: str | None
    bedrooms: int | None
    bathrooms: Decimal | None
    market_id: int | None
    deal_status: str
    deal_approved: datetime | None
    purchase_price: Decimal | None
    total_oop: Decimal
    l_cash_on_cash: Decimal | None
    m_cash_on_cash: Decimal | None
    h_cash_on_cash: Decimal | None
    y1_coc_incl_tax_savings_mid: Decimal | None
    tax_savings: Decimal | None
    mid_gross_revenue: Decimal | None
    down_payment_pct: Decimal | None
    interest_rate: Decimal | None
    boolean_tags: dict[str, bool]
    category_tags: dict[str, str | list[str] | None]


@dataclass(frozen=True)
class PoolResult:
    deals: list[CatalogDeal]
    dropped_unrecalculable: int


@dataclass(frozen=True)
class CatalogDealDetails:
    deal: CatalogDeal
    deal_pitch: str | None
    note: str | None
    analyst_notes: str | None
    construction_and_design_notes: str | None
    optimization_items: list[dict[str, Any]]
    comp_amenity_counts: dict[str, int]
    listing_url: str | None
    video_walkthrough: str | None
    loom_vid: str | None
    market_name: str | None


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _stored_terms_match(
    row: Any, down_payment_pct: Decimal | None, interest_rate: Decimal | None
) -> bool:
    stored = row.purchase_details
    if not stored or row.total_oop is None:
        return False
    for key, requested in (
        ("down_payment_pct", down_payment_pct),
        ("interest_rate", interest_rate),
    ):
        if requested is None:
            continue
        value = _decimal(stored.get(key))
        if value is None or abs(value - requested) > Decimal("0.0001"):
            return False
    return True


class DealCatalogService:
    def __init__(
        self,
        repository: UnderwritingRepository,
        calculator: UnderwritingCalculator | None = None,
    ):
        self.repository = repository
        self._simulator = SimulateUnderwritingsService(repository, calculator=calculator)

    @classmethod
    def for_session(cls, session: AsyncSession) -> "DealCatalogService":
        """Build on a session, so callers never import iron_bank's repository."""
        return cls(UnderwritingRepository(session))

    async def list_candidate_pool(
        self,
        *,
        statuses: Sequence[str],
        property_pending: bool | None = False,
        approved_from: date | None = None,
        approved_to: date | None = None,
        down_payment_pct: Decimal | None = None,
        interest_rate: Decimal | None = None,
    ) -> PoolResult:
        rows = await self.repository.get_recommendation_pool_rows(
            statuses=list(statuses),
            property_pending=property_pending,
            min_deal_approved=approved_from,
            max_deal_approved=approved_to,
        )
        return self._build_pool(rows, down_payment_pct, interest_rate)

    async def text_search(self, ids: Sequence[int], query: str) -> set[int]:
        terms = [term.lower() for term in query.split()]
        if not terms:
            return set(ids)
        return await self.repository.search_text(list(ids), terms)

    async def get_details(
        self,
        ids: Sequence[int],
        *,
        down_payment_pct: Decimal | None = None,
        interest_rate: Decimal | None = None,
    ) -> list[CatalogDealDetails]:
        if not ids:
            return []
        # Any status: details are only requested for ids a search already
        # returned, so the pool rules were applied there.
        rows = await self.repository.get_recommendation_pool_rows(
            statuses=[status.value for status in DealStatus], property_pending=None, ids=list(ids)
        )
        deals = {
            deal.id: deal
            for deal in self._build_pool(rows, down_payment_pct, interest_rate).deals
        }
        items = {item.id: item for item in await self.repository.get_by_ids(list(ids))}
        market_names = await self.repository.get_market_names(
            {deal.market_id for deal in deals.values() if deal.market_id is not None}
        )
        details = []
        for deal_id in ids:
            deal, item = deals.get(deal_id), items.get(deal_id)
            if deal is None or item is None:
                continue
            detail = item.detail
            details.append(
                CatalogDealDetails(
                    deal=deal,
                    deal_pitch=item.deal_pitch,
                    note=item.note,
                    analyst_notes=getattr(detail, "analyst_notes", None),
                    construction_and_design_notes=getattr(
                        detail, "construction_and_design_notes", None
                    ),
                    optimization_items=[
                        {
                            "category": oi.category,
                            "spec": oi.spec,
                            "tier": oi.tier,
                            "notes": oi.notes,
                            "total_price": oi.total_price,
                        }
                        for oi in item.optimization_items or []
                    ],
                    comp_amenity_counts={
                        field: sum(
                            1 for comp in item.comp_set or [] if getattr(comp, field) is True
                        )
                        for field in COMP_AMENITY_FIELDS
                    },
                    listing_url=item.listing_url,
                    video_walkthrough=item.video_walkthrough,
                    loom_vid=item.loom_vid,
                    market_name=market_names.get(deal.market_id),
                )
            )
        return details

    def _build_pool(
        self,
        rows: Sequence[Any],
        down_payment_pct: Decimal | None,
        interest_rate: Decimal | None,
    ) -> PoolResult:
        deals, dropped = [], 0
        for row in rows:
            simulated = self._simulator.simulate_row(row, interest_rate, down_payment_pct)
            if simulated.simulated:
                purchase_details = simulated.purchase_details or {}
                y1 = simulated.y1_coc_incl_tax_savings or {}
            elif _stored_terms_match(row, down_payment_pct, interest_rate):
                # Legacy rows whose stored JSON the calculator rejects: their
                # stored numbers are already at the requested terms, so they
                # are correct as-is (simulate_row fell back to them).
                purchase_details = row.purchase_details
                y1 = row.y1_coc_incl_tax_savings or {}
            else:
                dropped += 1
                continue
            deals.append(
                CatalogDeal(
                    id=row.id,
                    property_address=row.property_address,
                    street=row.street,
                    city=row.city,
                    state=row.state,
                    bedrooms=row.bedrooms,
                    bathrooms=row.bathrooms,
                    market_id=row.market_id,
                    deal_status=row.deal_status,
                    deal_approved=row.deal_approved,
                    purchase_price=row.purchase_price,
                    total_oop=simulated.total_oop,
                    l_cash_on_cash=simulated.l_cash_on_cash,
                    m_cash_on_cash=simulated.m_cash_on_cash,
                    h_cash_on_cash=simulated.h_cash_on_cash,
                    y1_coc_incl_tax_savings_mid=_decimal(y1.get("mid_pct")),
                    tax_savings=row.tax_savings,
                    mid_gross_revenue=row.mid_gross_revenue,
                    down_payment_pct=_decimal(purchase_details.get("down_payment_pct")),
                    interest_rate=_decimal(purchase_details.get("interest_rate")),
                    boolean_tags={
                        name: bool(getattr(row, name)) for name in BOOLEAN_TAG_FIELDS
                    },
                    category_tags={
                        name: getattr(row, name)
                        for name in (*MULTI_SELECT_TAG_FIELDS, *SINGLE_SELECT_TAG_FIELDS)
                    },
                )
            )
        return PoolResult(deals=deals, dropped_unrecalculable=dropped)

