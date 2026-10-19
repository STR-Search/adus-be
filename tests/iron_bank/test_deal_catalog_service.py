from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.iron_bank.services.deal_catalog_service import DealCatalogService


def _purchase_details(**overrides):
    stored = {
        "purchase_price": 500000,
        "down_payment_pct": 0.2,
        "interest_rate": 0.07,
        "mortgage_years": 30,
        "closing_costs_pct": 0.03,
        "down_payment_amount": 100000.0,
        "loan_amount": 400000.0,
        "closing_costs_amount": 15000.0,
    }
    stored.update(overrides)
    return stored


def _forecasted_revenue():
    return {
        "co_hosting_fee_pct": 0,
        "annual_re_appreciation_pct": 0.04,
        "scenarios": {
            "low": {"forecasted_revenue": 50000},
            "mid": {"forecasted_revenue": 60000},
            "high": {"forecasted_revenue": 70000},
        },
    }


def _row(id=1, purchase_details="default", forecasted_revenue="default", **overrides):
    fields = dict(
        id=id,
        source="legacy_sheet",
        prr=None,
        sheet_number=None,
        created_at=None,
        deal_approved=datetime(2026, 3, 1, tzinfo=timezone.utc),
        purchase_price=Decimal("500000"),
        total_oop=Decimal("140000"),
        l_cash_on_cash=Decimal("0.05"),
        m_cash_on_cash=Decimal("0.08"),
        h_cash_on_cash=Decimal("0.10"),
        budget_to_pp=Decimal("0.28"),
        optimization_total=Decimal("25000"),
        operating_expense_total=Decimal("1500"),
        purchase_details=(
            _purchase_details() if purchase_details == "default" else purchase_details
        ),
        forecasted_revenue=(
            _forecasted_revenue()
            if forecasted_revenue == "default"
            else forecasted_revenue
        ),
        tax_savings=Decimal("90000"),
        y1_coc_incl_tax_savings=None,
        property_address=f"{id} Main St, Largo, FL 33770",
        street=f"{id} Main St",
        city="Largo",
        state="FL",
        bedrooms=3,
        bathrooms=Decimal("2.0"),
        market_id=7,
        deal_status="present_to_clients",
        mid_gross_revenue=Decimal("60000"),
        turnkey=True,
        furnished=False,
        luxury=False,
        tax_efficient=False,
        new_construction=False,
        existing_airbnb=False,
        arv=False,
        high_cash_on_cash=False,
        low_cash_on_cash=False,
        add_inground_pool=False,
        waterfront=False,
        remote=False,
        can_support_cohost=False,
        market_type=["mountain"],
        execution_type=None,
        seasonality=None,
        regulatory_clarity=None,
        offer_competitiveness=None,
        core_value_driver=None,
        cash_flow_quality=None,
        view_quality=None,
        pool_type=None,
        primary_guest_avatar=None,
        target_demographic=None,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


class FakeRepository:
    def __init__(self, rows=(), items=(), market_names=None):
        self.rows = list(rows)
        self.items = {item.id: item for item in items}
        self.market_names = market_names or {}
        self.pool_filters = None
        self.text_calls = []

    async def get_recommendation_pool_rows(self, **filters):
        self.pool_filters = filters
        ids = filters.get("ids")
        return [r for r in self.rows if ids is None or r.id in ids]

    async def search_text(self, ids, terms):
        self.text_calls.append((list(ids), list(terms)))
        return {ids[0]}

    async def get_by_ids(self, ids):
        return [self.items[i] for i in ids if i in self.items]

    async def get_market_names(self, market_ids):
        return {m: self.market_names[m] for m in market_ids if m in self.market_names}


@pytest.mark.asyncio
async def test_pool_drops_rows_without_purchase_details_or_forecast():
    repo = FakeRepository(
        [_row(1), _row(2, purchase_details=None), _row(3, forecasted_revenue=None)]
    )
    # Requested terms (10% down) differ from row 3's stored 20%, so the row
    # that cannot be recalculated cannot fall back to its stored numbers.
    result = await DealCatalogService(repo).list_candidate_pool(
        statuses=["present_to_clients"], down_payment_pct=Decimal("0.1")
    )
    assert [d.id for d in result.deals] == [1]
    assert result.dropped_unrecalculable == 2


@pytest.mark.asyncio
async def test_pool_recalculates_at_requested_down_payment():
    repo = FakeRepository([_row(1)])
    service = DealCatalogService(repo)
    stored = (await service.list_candidate_pool(statuses=["present_to_clients"])).deals[0]
    simulated = (
        await service.list_candidate_pool(
            statuses=["present_to_clients"], down_payment_pct=Decimal("0.1")
        )
    ).deals[0]
    assert stored.down_payment_pct == Decimal("0.2")
    assert simulated.down_payment_pct == Decimal("0.1")
    assert simulated.total_oop < stored.total_oop
    assert simulated.tax_savings == Decimal("90000")
    assert simulated.boolean_tags["turnkey"] is True
    assert simulated.category_tags["market_type"] == ["mountain"]


@pytest.mark.asyncio
async def test_pool_passes_filters_to_repository():
    repo = FakeRepository([])
    await DealCatalogService(repo).list_candidate_pool(
        statuses=["present_to_clients", "client_under_contract"],
        property_pending=None,
        approved_from=date(2026, 2, 15),
        approved_to=date(2026, 5, 20),
    )
    assert repo.pool_filters["statuses"] == ["present_to_clients", "client_under_contract"]
    assert repo.pool_filters["property_pending"] is None
    assert repo.pool_filters["min_deal_approved"] == date(2026, 2, 15)
    assert repo.pool_filters["max_deal_approved"] == date(2026, 5, 20)


@pytest.mark.asyncio
async def test_text_search_splits_terms_and_lowercases():
    repo = FakeRepository()
    service = DealCatalogService(repo)
    assert await service.text_search([1, 2], "Pickleball  Lake") == {1}
    assert repo.text_calls == [([1, 2], ["pickleball", "lake"])]


@pytest.mark.asyncio
async def test_text_search_blank_query_matches_all_without_repo_call():
    repo = FakeRepository()
    assert await DealCatalogService(repo).text_search([1, 2], "   ") == {1, 2}
    assert repo.text_calls == []


@pytest.mark.asyncio
async def test_get_details_counts_comp_amenities():
    comps = [
        SimpleNamespace(has_pool=True, has_pickleball=True, has_hot_tub=None, has_sauna=None,
                        has_mini_golf=None, has_game_room=None, has_movie_theater=None,
                        has_playground=None, has_waterfront=None),
        SimpleNamespace(has_pool=True, has_pickleball=None, has_hot_tub=False, has_sauna=None,
                        has_mini_golf=None, has_game_room=None, has_movie_theater=None,
                        has_playground=None, has_waterfront=None),
    ]
    item = SimpleNamespace(
        id=1,
        deal_pitch="Great lake house",
        note=None,
        listing_url="https://example.com/1",
        video_walkthrough=None,
        loom_vid=None,
        market_id=7,
        detail=SimpleNamespace(analyst_notes="Add pickleball", construction_and_design_notes=None),
        optimization_items=[
            SimpleNamespace(category="Pickleball", spec="court", tier=None, notes=None,
                            total_price=Decimal("30000"))
        ],
        comp_set=comps,
    )
    repo = FakeRepository([_row(1)], items=[item], market_names={7: "Smokies"})
    details = await DealCatalogService(repo).get_details([1], down_payment_pct=Decimal("0.1"))
    assert len(details) == 1
    d = details[0]
    assert d.comp_amenity_counts["has_pool"] == 2
    assert d.comp_amenity_counts["has_pickleball"] == 1
    assert d.comp_amenity_counts["has_hot_tub"] == 0
    assert d.market_name == "Smokies"
    assert d.analyst_notes == "Add pickleball"
    assert d.optimization_items[0]["category"] == "Pickleball"
    assert d.deal.down_payment_pct == Decimal("0.1")


def _legacy_forecast():
    # Legacy-sheet shape: no annual_re_appreciation_pct, so it cannot be recalculated.
    return {"co_hosting_fee_pct": 0, "scenarios": {"mid": {"forecasted_revenue": 60000}}}


@pytest.mark.asyncio
async def test_unrecalculable_row_kept_with_stored_numbers_when_stored_terms_match():
    row = _row(
        1,
        purchase_details=_purchase_details(down_payment_pct=0.1),
        forecasted_revenue=_legacy_forecast(),
        y1_coc_incl_tax_savings={"mid_pct": 0.61},
    )
    result = await DealCatalogService(FakeRepository([row])).list_candidate_pool(
        statuses=["present_to_clients"], down_payment_pct=Decimal("0.1")
    )
    assert [d.id for d in result.deals] == [1]
    deal = result.deals[0]
    assert deal.total_oop == Decimal("140000")
    assert deal.down_payment_pct == Decimal("0.1")
    assert deal.y1_coc_incl_tax_savings_mid == Decimal("0.61")
    assert result.dropped_unrecalculable == 0


@pytest.mark.asyncio
async def test_unrecalculable_row_dropped_when_requested_terms_differ():
    row = _row(1, forecasted_revenue=_legacy_forecast())  # stored at 20% down
    result = await DealCatalogService(FakeRepository([row])).list_candidate_pool(
        statuses=["present_to_clients"], down_payment_pct=Decimal("0.1")
    )
    assert result.deals == []
    assert result.dropped_unrecalculable == 1
