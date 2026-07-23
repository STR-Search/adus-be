from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.iron_bank.enums import SortOrder, UnderwritingSortBy
from app.iron_bank.services.simulate_underwritings_service import (
    SimulateUnderwritingsService,
)


class FakeSimulationRepository:
    """Serves the lean simulation-input rows and the hydrated page fetch."""

    def __init__(self, rows, items_by_id=None):
        self.rows = rows
        self.items_by_id = items_by_id or {}
        self.sim_filters = None
        self.requested_ids = None

    async def get_simulation_inputs(self, **filters):
        self.sim_filters = filters
        return self.rows

    async def get_by_ids(self, ids):
        self.requested_ids = list(ids)
        # Deliberately return in reversed order: WHERE id IN (...) gives DB
        # order, and the service must restore its own computed order.
        return [self.items_by_id[i] for i in reversed(ids) if i in self.items_by_id]


def _stored_purchase_details(**overrides):
    # Floats/ints, as JSONB hands them back.
    stored = {
        "purchase_price": 100000,
        "down_payment_pct": 0.2,
        "interest_rate": 0.07,
        "mortgage_years": 30,
        "closing_costs_pct": 0.03,
        "down_payment_amount": 20000.0,
        "loan_amount": 80000.0,
        "closing_costs_amount": 3000.0,
    }
    stored.update(overrides)
    return stored


def _stored_forecasted_revenue():
    return {
        "co_hosting_fee_pct": 0,
        "annual_re_appreciation_pct": 0.04,
        "scenarios": {
            "low": {"forecasted_revenue": 50000},
            "mid": {"forecasted_revenue": 60000},
            "high": {"forecasted_revenue": 70000},
        },
    }


def _row(
    id=1,
    purchase_price=Decimal("100000"),
    total_oop=Decimal("30000"),
    l_cash_on_cash=Decimal("0.5"),
    optimization_total=Decimal("7000"),
    operating_expense_total=Decimal("1000"),
    purchase_details="default",
    forecasted_revenue="default",
    tax_savings=Decimal("5000"),
):
    return SimpleNamespace(
        id=id,
        purchase_price=purchase_price,
        total_oop=total_oop,
        l_cash_on_cash=l_cash_on_cash,
        optimization_total=optimization_total,
        operating_expense_total=operating_expense_total,
        purchase_details=(
            _stored_purchase_details() if purchase_details == "default" else purchase_details
        ),
        forecasted_revenue=(
            _stored_forecasted_revenue()
            if forecasted_revenue == "default"
            else forecasted_revenue
        ),
        tax_savings=tax_savings,
    )


def _item(id=1, **fields):
    """Minimal hydrated underwriting for the page-fetch phase."""
    defaults = dict(
        id=id,
        detail=None,
        taxes=None,
        optimization_items=[],
        operating_expenses=[],
        comp_set=[],
        is_automated=None,
        zpid=None,
        # Non-nullable bools on UnderwritingRead; _parent_data copies them
        # explicitly, so the fake must carry real values.
        property_pending=False,
        turnkey=False,
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
    )
    defaults.update(fields)
    return SimpleNamespace(**defaults)


def _service(rows, items_by_id=None):
    repository = FakeSimulationRepository(rows, items_by_id)
    return SimulateUnderwritingsService(repository), repository


async def _get_all_simulated(service, **kwargs):
    params = dict(page=1, page_size=20)
    params.update(kwargs)
    return await service.get_all_simulated(**params)


# --- Recalculation ---------------------------------------------------------
#
# Hand-computed expectations with interest_rate=0 and down_payment_pct=0.1
# overrides on the default row (purchase_price 100k, closing 3%, 30y mortgage,
# optimization total 7000, monthly opex total 1000, tax_savings 5000):
#
#   down_payment = 10000, loan = 90000, closing = 3000
#   total_oop    = 10000 + 3000 + 7000 = 20000
#   budget_to_pp = 20000 / 100000 = 0.2
#   debt_service = 90000 / 30 = 3000/yr (zero-rate amortization)
#   mid:  NOI = 60000 - 12000            = 48000; CoC = 45000/20000 = 2.25
#   low:  NOI = 50000 - 11520 (0.96x)    = 38480; CoC = 35480/20000 = 1.774
#   high: NOI = 70000 - 12480 (1.04x)    = 57520; CoC = 54520/20000 = 2.726
#   y1 (mid): (48000 - 3000 + 5000) / 20000 = 2.5


@pytest.mark.asyncio
async def test_simulates_metrics_with_both_overrides():
    service, _ = _service([_row(id=1)], {1: _item(id=1)})

    result = await _get_all_simulated(
        service, interest_rate=Decimal("0"), down_payment_pct=Decimal("0.1")
    )

    assert result.total == 1
    row = result.data[0]
    assert row.simulated is True
    assert row.total_oop == Decimal("20000")
    assert row.budget_to_pp == Decimal("0.2000")
    assert row.l_cash_on_cash == Decimal("1.7740")
    assert row.m_cash_on_cash == Decimal("2.2500")
    assert row.h_cash_on_cash == Decimal("2.7260")
    # Echo block reflects the applied overrides.
    assert result.simulation.interest_rate == Decimal("0")
    assert result.simulation.down_payment_pct == Decimal("0.1")


@pytest.mark.asyncio
async def test_overlays_recalculated_detail_json():
    service, _ = _service([_row(id=1)], {1: _item(id=1)})

    result = await _get_all_simulated(
        service, interest_rate=Decimal("0"), down_payment_pct=Decimal("0.1")
    )

    details = result.data[0].details
    # purchase_details: overrides merged, financing amounts recalculated,
    # untouched stored inputs preserved.
    assert details.purchase_details["down_payment_pct"] == 0.1
    assert details.purchase_details["interest_rate"] == 0
    assert details.purchase_details["down_payment_amount"] == 10000.0
    assert details.purchase_details["loan_amount"] == 90000.0
    assert details.purchase_details["closing_costs_amount"] == 3000.0
    assert details.purchase_details["mortgage_years"] == 30
    # forecasted_revenue scenarios recalculated with the new financing.
    mid = details.forecasted_revenue["scenarios"]["mid"]
    assert mid["debt_service_annual"] == 3000.0
    assert mid["net_operating_income"] == 48000.0
    assert mid["annual_free_cash_flow"] == 45000.0
    # y1 CoC incl tax savings recomputed from stored tax_savings.
    assert details.y1_coc_incl_tax_savings["mid_pct"] == 2.5


@pytest.mark.asyncio
async def test_interest_only_override_keeps_total_oop():
    service, _ = _service([_row(id=1)], {1: _item(id=1)})

    result = await _get_all_simulated(service, interest_rate=Decimal("0"))

    row = result.data[0]
    # Stored down_payment_pct (0.2) still applies: 20000 + 3000 + 7000.
    assert row.total_oop == Decimal("30000")
    assert row.budget_to_pp == Decimal("0.3000")
    # Zero interest still moves cash-on-cash: loan = 80000 (stored 20% down),
    # debt = 80000/30 = 2666.67, mid FCF = 48000 - 2666.67 = 45333.33.
    assert row.m_cash_on_cash == Decimal("1.5111")


@pytest.mark.asyncio
async def test_uses_stored_collection_totals():
    lean = _row(id=1, optimization_total=None, operating_expense_total=None)
    service, _ = _service([lean], {1: _item(id=1)})

    result = await _get_all_simulated(
        service, interest_rate=Decimal("0"), down_payment_pct=Decimal("0.1")
    )

    row = result.data[0]
    # No optimization rows: total_oop = 10000 + 3000; no opex: NOI = revenue.
    assert row.total_oop == Decimal("13000")
    assert row.m_cash_on_cash == Decimal("4.3846")  # (60000 - 3000) / 13000


# --- Include-and-flag ------------------------------------------------------


@pytest.mark.asyncio
async def test_flags_rows_missing_inputs_and_keeps_stored_values():
    rows = [
        _row(id=1, purchase_details=None),
        _row(id=2, forecasted_revenue=None),
    ]
    service, _ = _service(rows, {1: _item(id=1), 2: _item(id=2)})

    result = await _get_all_simulated(service, interest_rate=Decimal("0.05"))

    assert result.total == 2
    assert all(row.simulated is False for row in result.data)
    # Stored fallback values are what the row displays/sorts/filters by; the
    # hydrated result keeps its own stored columns (None on these fakes).
    assert all(row.details is None for row in result.data)


@pytest.mark.asyncio
async def test_flags_zero_total_oop_instead_of_failing():
    row = _row(
        id=1,
        purchase_details=_stored_purchase_details(closing_costs_pct=0),
        optimization_total=None,
    )
    service, _ = _service([row], {1: _item(id=1)})

    result = await _get_all_simulated(service, down_payment_pct=Decimal("0"))

    assert result.data[0].simulated is False


# --- Filtering / sorting / pagination on simulated values -------------------


@pytest.mark.asyncio
async def test_filters_on_simulated_cash_on_cash():
    # Same stored economics; only the down-payment override differentiates
    # them: id=1 keeps opex low CoC 1.774, id=2 has double opex -> lower CoC.
    rows = [
        _row(id=1),
        _row(id=2, operating_expense_total=Decimal("4000")),
    ]
    service, repository = _service(rows, {1: _item(id=1), 2: _item(id=2)})

    result = await _get_all_simulated(
        service,
        interest_rate=Decimal("0"),
        down_payment_pct=Decimal("0.1"),
        min_l_cash_on_cash=Decimal("1.0"),
    )

    # id=2: low NOI = 50000 - 46080 = 3920; FCF = 920; CoC = 0.046 -> filtered.
    assert result.total == 1
    assert [row.id for row in result.data] == [1]
    # The affected bound must NOT have been pushed down to SQL.
    assert "min_l_cash_on_cash" not in repository.sim_filters
    assert repository.sim_filters["market_id"] is None


@pytest.mark.asyncio
async def test_sorts_on_simulated_values_with_null_and_stored_fallbacks():
    rows = [
        _row(id=1),  # simulated, l_coc 1.774
        _row(id=2, purchase_details=None, l_cash_on_cash=None),  # flagged, null
        _row(id=3, purchase_details=None, l_cash_on_cash=Decimal("5.0")),  # flagged
    ]
    items = {i: _item(id=i) for i in (1, 2, 3)}
    service, _ = _service(rows, items)

    result = await _get_all_simulated(
        service,
        interest_rate=Decimal("0"),
        down_payment_pct=Decimal("0.1"),
        sort_by=UnderwritingSortBy.L_CASH_ON_CASH,
        sort_order=SortOrder.DESC,
    )

    # Postgres DESC semantics: nulls first, then values descending.
    assert [row.id for row in result.data] == [2, 3, 1]

    result = await _get_all_simulated(
        service,
        interest_rate=Decimal("0"),
        down_payment_pct=Decimal("0.1"),
        sort_by=UnderwritingSortBy.L_CASH_ON_CASH,
        sort_order=SortOrder.ASC,
    )
    assert [row.id for row in result.data] == [1, 3, 2]


@pytest.mark.asyncio
async def test_sort_ties_break_by_id_desc():
    rows = [_row(id=1), _row(id=2), _row(id=3)]
    items = {i: _item(id=i) for i in (1, 2, 3)}
    service, _ = _service(rows, items)

    result = await _get_all_simulated(
        service,
        interest_rate=Decimal("0"),
        sort_by=UnderwritingSortBy.L_CASH_ON_CASH,
        sort_order=SortOrder.ASC,
    )

    assert [row.id for row in result.data] == [3, 2, 1]


@pytest.mark.asyncio
async def test_paginates_after_filter_and_sort():
    rows = [_row(id=i) for i in (1, 2, 3)]
    items = {i: _item(id=i) for i in (1, 2, 3)}
    service, repository = _service(rows, items)

    result = await _get_all_simulated(
        service,
        page=2,
        page_size=2,
        interest_rate=Decimal("0"),
        sort_by=UnderwritingSortBy.ID,
        sort_order=SortOrder.DESC,
    )

    assert result.total == 3
    assert result.pages == 2
    assert [row.id for row in result.data] == [1]
    # Only the page was hydrated.
    assert repository.requested_ids == [1]


@pytest.mark.asyncio
async def test_restores_computed_order_after_hydration():
    rows = [_row(id=i) for i in (1, 2, 3)]
    items = {i: _item(id=i) for i in (1, 2, 3)}
    service, _ = _service(rows, items)

    # The fake returns hydrated rows reversed; order must still be id DESC.
    result = await _get_all_simulated(
        service,
        interest_rate=Decimal("0"),
        sort_by=UnderwritingSortBy.ID,
        sort_order=SortOrder.DESC,
    )

    assert [row.id for row in result.data] == [3, 2, 1]


# --- Response contract ------------------------------------------------------


@pytest.mark.asyncio
async def test_simulated_flag_serializes_only_in_simulation_mode():
    service, _ = _service([_row(id=1)], {1: _item(id=1)})

    result = await _get_all_simulated(service, interest_rate=Decimal("0"))

    dumped = result.model_dump()
    assert dumped["simulation"] == {
        "interest_rate": Decimal("0"),
        "down_payment_pct": None,
    }
    assert dumped["data"][0]["simulated"] is True

    from app.iron_bank.schemas.get_underwriting import (
        GetUnderwritingResult,
        GetUnderwritingsResult,
    )

    plain = GetUnderwritingsResult(
        data=[GetUnderwritingResult(id=1)], total=1, page=1, page_size=20, pages=1
    ).model_dump()
    assert "simulation" not in plain
    assert "simulated" not in plain["data"][0]
