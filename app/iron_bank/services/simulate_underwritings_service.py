import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from app.core.logger import logger
from app.iron_bank.enums import SortOrder, UnderwritingSortBy
from app.iron_bank.schemas.get_underwriting import (
    GetUnderwritingDetails,
    GetUnderwritingsResult,
    SimulationParams,
)
from app.iron_bank.schemas.save_underwriting import (
    ForecastedRevenueInput,
    OperatingExpenseInput,
    OptimizationItemInput,
    PurchaseDetailsInput,
)
from app.iron_bank.services.get_underwriting_service import GetUnderwritingService
from app.iron_bank.services.underwriting_calculator import UnderwritingCalculator


@dataclass
class _SimulatedRow:
    """One candidate row after the Python recalculation pass.

    ``simulated`` is False when the row lacked the inputs to recalculate; its
    displayed values then fall back to the stored ones so it can still be
    filtered, sorted, and returned (include-and-flag semantics).
    """

    id: int
    simulated: bool
    # Displayed values (simulated when available, stored otherwise).
    purchase_price: Decimal | None
    total_oop: Decimal | None
    l_cash_on_cash: Decimal | None
    # Simulated-only outputs, overlaid onto the hydrated page results.
    m_cash_on_cash: Decimal | None = None
    h_cash_on_cash: Decimal | None = None
    budget_to_pp: Decimal | None = None
    purchase_details: dict[str, Any] | None = None
    forecasted_revenue: dict[str, Any] | None = None
    y1_coc_incl_tax_savings: dict[str, Any] | None = None


class SimulateUnderwritingsService(GetUnderwritingService):
    """Read-only 'what if' view over the underwritings list.

    Recalculates every financing-derived metric with overridden
    ``interest_rate`` and/or ``down_payment_pct`` — via the same
    ``UnderwritingCalculator`` the save/update paths use — and runs the
    affected filters, sorting, and pagination on the simulated values.
    Nothing is persisted.

    Two-phase fetch: a lean full-set query supplies the calculation inputs
    (financing math is non-linear in the interest rate, so recalculation must
    precede sorting); only the resulting page is fully hydrated and enriched,
    exactly like ``GetUnderwritingService.get_all``.
    """

    def __init__(self, *args, calculator: UnderwritingCalculator | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.calculator = calculator or UnderwritingCalculator()

    async def get_all_simulated(
        self,
        *,
        page: int,
        page_size: int,
        zpid: str | None = None,
        market_id: int | None = None,
        deal_status: str | None = None,
        analyst_id: int | None = None,
        min_purchase_price: Decimal | None = None,
        max_purchase_price: Decimal | None = None,
        min_total_oop: Decimal | None = None,
        max_total_oop: Decimal | None = None,
        min_l_cash_on_cash: Decimal | None = None,
        max_l_cash_on_cash: Decimal | None = None,
        sort_by: UnderwritingSortBy = UnderwritingSortBy.ID,
        sort_order: SortOrder = SortOrder.DESC,
        interest_rate: Decimal | None = None,
        down_payment_pct: Decimal | None = None,
    ) -> GetUnderwritingsResult:
        rows = await self.repository.get_simulation_inputs(
            zpid=zpid,
            market_id=market_id,
            deal_status=deal_status,
            analyst_id=analyst_id,
            min_purchase_price=min_purchase_price,
            max_purchase_price=max_purchase_price,
        )

        simulated_rows = [
            self._simulate_row(row, interest_rate, down_payment_pct) for row in rows
        ]

        filtered = [
            row
            for row in simulated_rows
            if self._passes_bounds(row.total_oop, min_total_oop, max_total_oop)
            and self._passes_bounds(
                row.l_cash_on_cash, min_l_cash_on_cash, max_l_cash_on_cash
            )
        ]

        total = len(filtered)
        pages = math.ceil(total / page_size) if page_size > 0 else 0

        self._sort(filtered, sort_by=sort_by, sort_order=sort_order)
        page_rows = filtered[(page - 1) * page_size : page * page_size]

        # Hydrate the page only; restore the Python-computed order (the IN
        # query returns DB order).
        items = await self.repository.get_by_ids([row.id for row in page_rows])
        items_by_id = {item.id: item for item in items}
        items = [items_by_id[row.id] for row in page_rows if row.id in items_by_id]

        results = [self._to_result(underwriting) for underwriting in items]
        await self._hydrate_automated_zillow(items, results)
        await self._populate_reference_labels(results)

        rows_by_id = {row.id: row for row in page_rows}
        for result in results:
            self._overlay_simulated(result, rows_by_id[result.id])

        return GetUnderwritingsResult(
            data=results,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
            simulation=SimulationParams(
                interest_rate=interest_rate,
                down_payment_pct=down_payment_pct,
            ),
        )

    def _simulate_row(
        self,
        row: Any,
        interest_rate: Decimal | None,
        down_payment_pct: Decimal | None,
    ) -> _SimulatedRow:
        """Recalculate one row; fall back to stored values when it can't be.

        Any missing/invalid input (no purchase_details, no forecasted_revenue,
        zero total_oop, malformed stored JSON, ...) flags the row rather than
        failing the request.
        """
        fallback = _SimulatedRow(
            id=row.id,
            simulated=False,
            purchase_price=row.purchase_price,
            total_oop=row.total_oop,
            l_cash_on_cash=row.l_cash_on_cash,
        )
        try:
            return self._calculate_simulated_row(row, interest_rate, down_payment_pct)
        except (ValueError, KeyError, TypeError, ValidationError) as e:
            logger.debug(
                "iron_bank.simulate_underwritings.row_not_simulatable",
                underwriting_id=row.id,
                reason=str(e),
            )
            return fallback

    def _calculate_simulated_row(
        self,
        row: Any,
        interest_rate: Decimal | None,
        down_payment_pct: Decimal | None,
    ) -> _SimulatedRow:
        if not row.purchase_details or not row.forecasted_revenue:
            raise ValueError(
                "stored purchase_details and forecasted_revenue are required"
            )

        merged = dict(row.purchase_details)
        if interest_rate is not None:
            merged["interest_rate"] = interest_rate
        if down_payment_pct is not None:
            merged["down_payment_pct"] = down_payment_pct
        purchase_details = self.calculator.calculate_purchase_details(
            PurchaseDetailsInput.model_validate(merged)
        )

        # The calculator only ever sums the collections, so one synthetic item
        # carrying each stored total is equivalent to the full child row sets —
        # and always reflects the STORED collections, never payload-local ones.
        optimization_items = [
            OptimizationItemInput(total_price=row.optimization_total or Decimal("0"))
        ]
        operating_expenses = [
            OperatingExpenseInput(
                monthly_amount=row.operating_expense_total or Decimal("0")
            )
        ]

        forecasted_revenue = self.calculator.calculate_forecasted_revenue(
            forecasted_revenue=ForecastedRevenueInput.model_validate(
                row.forecasted_revenue
            ),
            purchase_details=purchase_details,
            operating_expenses=operating_expenses,
            optimization_items=optimization_items,
        )
        total_oop = self.calculator.calculate_total_oop(
            purchase_details=purchase_details,
            optimization_items=optimization_items,
        )
        cash_on_cash = self.calculator.calculate_cash_on_cash(
            forecasted_revenue=forecasted_revenue,
            total_oop=total_oop,
        )
        budget_to_pp = self.calculator.calculate_budget_to_pp(
            total_oop=total_oop,
            purchase_price=purchase_details["purchase_price"],
        )
        y1_coc_incl_tax_savings = (
            self.calculator.calculate_y1_coc_incl_tax_savings(
                forecasted_revenue=forecasted_revenue,
                tax_data={"tax_savings": row.tax_savings},
                purchase_details=purchase_details,
                optimization_items=optimization_items,
            )
            if row.tax_savings is not None
            else None
        )

        return _SimulatedRow(
            id=row.id,
            simulated=True,
            purchase_price=row.purchase_price,
            total_oop=total_oop,
            l_cash_on_cash=cash_on_cash["low_pct"],
            m_cash_on_cash=cash_on_cash["mid_pct"],
            h_cash_on_cash=cash_on_cash["high_pct"],
            budget_to_pp=budget_to_pp,
            purchase_details=purchase_details,
            forecasted_revenue=forecasted_revenue,
            y1_coc_incl_tax_savings=y1_coc_incl_tax_savings,
        )

    @staticmethod
    def _passes_bounds(
        value: Decimal | None,
        minimum: Decimal | None,
        maximum: Decimal | None,
    ) -> bool:
        # NULL fails any bound — same outcome as the SQL comparisons on the
        # non-simulated path.
        if minimum is not None and (value is None or value < minimum):
            return False
        if maximum is not None and (value is None or value > maximum):
            return False
        return True

    @staticmethod
    def _sort(
        rows: list[_SimulatedRow],
        *,
        sort_by: UnderwritingSortBy,
        sort_order: SortOrder,
    ) -> None:
        """In-place sort mirroring the SQL path's semantics.

        Postgres null placement (nulls sort as largest: first on DESC, last on
        ASC) and the ``id DESC`` tiebreaker, so switching simulation on/off
        never reshuffles rows the simulation didn't affect.
        """

        def sort_value(row: _SimulatedRow) -> Decimal | int | None:
            return getattr(row, sort_by.value)

        descending = sort_order == SortOrder.DESC

        def key(row: _SimulatedRow):
            value = sort_value(row)
            if value is None:
                # Nulls as largest: rank 0 on DESC (first), 2 on ASC (last).
                null_rank, sortable = (0 if descending else 2), Decimal("0")
            else:
                null_rank, sortable = 1, (-value if descending else value)
            return (null_rank, sortable, -row.id)

        rows.sort(key=key)

    @staticmethod
    def _overlay_simulated(result, row: _SimulatedRow) -> None:
        """Write the recalculated values onto a hydrated page result.

        Deep overlay: the top-level metrics AND the detail JSON they were
        derived from move together, so the response stays internally
        consistent. Flagged rows only receive the ``simulated`` marker.
        """
        result.simulated = row.simulated
        if not row.simulated:
            return

        result.total_oop = row.total_oop
        result.budget_to_pp = row.budget_to_pp
        result.l_cash_on_cash = row.l_cash_on_cash
        result.m_cash_on_cash = row.m_cash_on_cash
        result.h_cash_on_cash = row.h_cash_on_cash

        if result.details is None:
            result.details = GetUnderwritingDetails()
        # jsonable_encoder mirrors how the save path persists these dicts
        # (Decimal -> float), keeping the simulated JSON shape identical to
        # the stored-JSON shape the FE already consumes.
        result.details.purchase_details = jsonable_encoder(row.purchase_details)
        result.details.forecasted_revenue = jsonable_encoder(row.forecasted_revenue)
        result.details.y1_coc_incl_tax_savings = (
            jsonable_encoder(row.y1_coc_incl_tax_savings)
            if row.y1_coc_incl_tax_savings is not None
            else result.details.y1_coc_incl_tax_savings
        )
