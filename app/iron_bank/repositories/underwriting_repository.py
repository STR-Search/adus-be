import math
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.iron_bank.enums import SortOrder, UnderwritingSortBy
from app.iron_bank.models import (
    Underwriting,
    UnderwritingCompSet,
    UnderwritingDetail,
    UnderwritingOperatingExpense,
    UnderwritingOptimizationItem,
    UnderwritingTax,
)


class UnderwritingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, underwriting_id: int) -> Underwriting | None:
        result = await self.db.execute(
            select(Underwriting)
            .where(Underwriting.id == underwriting_id)
            .options(
                selectinload(Underwriting.detail),
                selectinload(Underwriting.taxes),
                selectinload(Underwriting.optimization_items),
                selectinload(Underwriting.operating_expenses),
                selectinload(Underwriting.comp_set),
            )
        )
        return result.scalar_one_or_none()

    async def get_all_paginated(
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
    ) -> tuple[list[Underwriting], int, int]:
        """Returns (items, total, pages) ordered by newest underwriting first."""
        query = select(Underwriting)
        if zpid is not None:
            query = query.where(Underwriting.zpid == zpid)
        if market_id is not None:
            query = query.where(Underwriting.market_id == market_id)
        if deal_status is not None:
            query = query.where(Underwriting.deal_status == deal_status)
        if analyst_id is not None:
            query = query.where(Underwriting.analyst_id == analyst_id)
        if min_purchase_price is not None:
            query = query.where(Underwriting.purchase_price >= min_purchase_price)
        if max_purchase_price is not None:
            query = query.where(Underwriting.purchase_price <= max_purchase_price)
        if min_total_oop is not None:
            query = query.where(Underwriting.total_oop >= min_total_oop)
        if max_total_oop is not None:
            query = query.where(Underwriting.total_oop <= max_total_oop)
        if min_l_cash_on_cash is not None:
            query = query.where(Underwriting.l_cash_on_cash >= min_l_cash_on_cash)
        if max_l_cash_on_cash is not None:
            query = query.where(Underwriting.l_cash_on_cash <= max_l_cash_on_cash)

        total: int = (
            await self.db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()
        pages = math.ceil(total / page_size) if page_size > 0 else 0

        # Sort in-DB before pagination so ordering spans the whole result set,
        # not just the current page. sort_by is an enum, so getattr only ever
        # resolves a known column. id is appended as a stable tiebreaker for
        # the nullable/non-unique sort columns, keeping pagination deterministic.
        sort_column = getattr(Underwriting, sort_by.value)
        primary = (
            sort_column.desc() if sort_order == SortOrder.DESC else sort_column.asc()
        )

        result = await self.db.execute(
            query.options(
                selectinload(Underwriting.detail),
                selectinload(Underwriting.taxes),
                selectinload(Underwriting.optimization_items),
                selectinload(Underwriting.operating_expenses),
                selectinload(Underwriting.comp_set),
            )
            .order_by(primary, Underwriting.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(result.scalars().all())
        return items, total, pages

    async def get_simulation_inputs(
        self,
        *,
        zpid: str | None = None,
        market_id: int | None = None,
        deal_status: str | None = None,
        analyst_id: int | None = None,
        min_purchase_price: Decimal | None = None,
        max_purchase_price: Decimal | None = None,
    ) -> list[Any]:
        """Lean full-set fetch of per-row simulation inputs.

        Simulation must recalculate financing-derived metrics for the *whole*
        filtered set before it can filter/sort/paginate on them, so this
        deliberately returns thin rows (no child selectinloads, no pagination):
        stored fallback values for sort/filter, the detail JSON calculation
        inputs, and the child-collection totals the calculator sums over.

        Only filters that simulation does NOT change are applied here; the
        total_oop / l_cash_on_cash bounds are applied by the service in Python
        against the simulated values (filtering them in SQL would compare
        stored values and wrongly include/exclude rows).
        """
        query = (
            select(
                Underwriting.id,
                Underwriting.purchase_price,
                Underwriting.total_oop,
                Underwriting.l_cash_on_cash,
                Underwriting.optimization_total,
                Underwriting.operating_expense_total,
                UnderwritingDetail.purchase_details,
                UnderwritingDetail.forecasted_revenue,
                UnderwritingTax.tax_savings,
            )
            .outerjoin(
                UnderwritingDetail,
                UnderwritingDetail.underwriting_id == Underwriting.id,
            )
            .outerjoin(
                UnderwritingTax,
                UnderwritingTax.underwriting_id == Underwriting.id,
            )
        )
        if zpid is not None:
            query = query.where(Underwriting.zpid == zpid)
        if market_id is not None:
            query = query.where(Underwriting.market_id == market_id)
        if deal_status is not None:
            query = query.where(Underwriting.deal_status == deal_status)
        if analyst_id is not None:
            query = query.where(Underwriting.analyst_id == analyst_id)
        if min_purchase_price is not None:
            query = query.where(Underwriting.purchase_price >= min_purchase_price)
        if max_purchase_price is not None:
            query = query.where(Underwriting.purchase_price <= max_purchase_price)

        result = await self.db.execute(query)
        return list(result.all())

    async def get_by_ids(self, ids: list[int]) -> list[Underwriting]:
        """Fully hydrated rows for one page of ids.

        ``WHERE id IN (...)`` returns rows in DB order, not input order — the
        caller (simulation service) restores its Python-computed ordering.
        """
        if not ids:
            return []
        result = await self.db.execute(
            select(Underwriting)
            .where(Underwriting.id.in_(ids))
            .options(
                selectinload(Underwriting.detail),
                selectinload(Underwriting.taxes),
                selectinload(Underwriting.optimization_items),
                selectinload(Underwriting.operating_expenses),
                selectinload(Underwriting.comp_set),
            )
        )
        return list(result.scalars().all())

    async def get_by_listing_url(self, listing_url: str) -> Underwriting | None:
        result = await self.db.execute(
            select(Underwriting)
            .where(Underwriting.listing_url == listing_url)
            .order_by(Underwriting.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_zpid(self, zpid: str) -> Underwriting | None:
        result = await self.db.execute(
            select(Underwriting)
            .where(Underwriting.zpid == zpid)
            .options(
                selectinload(Underwriting.detail),
                selectinload(Underwriting.taxes),
                selectinload(Underwriting.optimization_items),
                selectinload(Underwriting.operating_expenses),
                selectinload(Underwriting.comp_set),
            )
            .order_by(Underwriting.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        underwriting_data: dict[str, Any],
        detail_data: dict[str, Any] | None = None,
        tax_data: dict[str, Any] | None = None,
        optimization_items: list[dict[str, Any]] | None = None,
        operating_expenses: list[dict[str, Any]] | None = None,
        comp_set: list[dict[str, Any]] | None = None,
    ) -> Underwriting:
        try:
            underwriting = Underwriting(**underwriting_data)
            self.db.add(underwriting)
            await self.db.flush()

            if detail_data:
                self.db.add(
                    UnderwritingDetail(
                        underwriting_id=underwriting.id,
                        **detail_data,
                    )
                )

            if tax_data:
                self.db.add(
                    UnderwritingTax(
                        underwriting_id=underwriting.id,
                        **tax_data,
                    )
                )

            # id may be present on the shared input schema (used by update for
            # in-place matching); on create there is nothing to match, so drop
            # it and let the sequence assign a fresh primary key. sort_order is
            # server-assigned from payload position, never client-supplied.
            for index, item in enumerate(optimization_items or []):
                self.db.add(
                    UnderwritingOptimizationItem(
                        underwriting_id=underwriting.id,
                        sort_order=index,
                        **{k: v for k, v in item.items() if k != "id"},
                    )
                )

            for index, expense in enumerate(operating_expenses or []):
                self.db.add(
                    UnderwritingOperatingExpense(
                        underwriting_id=underwriting.id,
                        sort_order=index,
                        **{k: v for k, v in expense.items() if k != "id"},
                    )
                )

            for index, comp in enumerate(comp_set or []):
                self.db.add(
                    UnderwritingCompSet(
                        underwriting_id=underwriting.id,
                        sort_order=index,
                        **{k: v for k, v in comp.items() if k != "id"},
                    )
                )

            await self.db.commit()
            await self.db.refresh(underwriting)
            return underwriting
        except Exception:
            await self.db.rollback()
            raise

    async def update(
        self,
        underwriting_id: int,
        underwriting_data: dict[str, Any],
        detail_data: dict[str, Any] | None = None,
        tax_data: dict[str, Any] | None = None,
        optimization_items: list[dict[str, Any]] | None = None,
        operating_expenses: list[dict[str, Any]] | None = None,
        comp_set: list[dict[str, Any]] | None = None,
    ) -> Underwriting | None:
        try:
            underwriting = await self.get_by_id(underwriting_id)
            if underwriting is None:
                return None

            self._update_model_fields(underwriting, underwriting_data)
            if detail_data is not None:
                self._upsert_detail(underwriting, detail_data)
            if tax_data is not None:
                self._upsert_taxes(underwriting, tax_data)
            if optimization_items is not None:
                await self._upsert_children(
                    model=UnderwritingOptimizationItem,
                    underwriting_id=underwriting_id,
                    existing_rows=underwriting.optimization_items,
                    incoming=optimization_items,
                )
            if operating_expenses is not None:
                await self._upsert_children(
                    model=UnderwritingOperatingExpense,
                    underwriting_id=underwriting_id,
                    existing_rows=underwriting.operating_expenses,
                    incoming=operating_expenses,
                )
            if comp_set is not None:
                await self._upsert_children(
                    model=UnderwritingCompSet,
                    underwriting_id=underwriting_id,
                    existing_rows=underwriting.comp_set,
                    incoming=comp_set,
                )

            await self.db.commit()
            await self.db.refresh(underwriting)
            return underwriting
        except Exception:
            await self.db.rollback()
            raise

    async def bulk_sync_property_pending(self) -> int:
        """Reconcile ``property_pending`` across all underwritings in one pass.

        Mirrors the save-time rule in
        ``SaveUnderwritingService._apply_listing_boolean_fields``
        (``home_status != "FOR_SALE"``, so a NULL status is also pending) as a
        set-based ``UPDATE ... FROM`` join on ``zpid``. ``IS DISTINCT FROM
        'FOR_SALE'`` is the null-safe form: true for NULL and any non-FOR_SALE
        value, false only for exactly ``FOR_SALE``. Underwritings whose ``zpid``
        has no matching scheduled listing are left untouched, and the second
        ``IS DISTINCT FROM`` guard writes only rows whose flag actually changes,
        so ``rowcount`` reports the number updated. Raw SQL (rather than the ORM)
        keeps this repository from importing the ``zillow`` domain's model.
        """
        try:
            result = await self.db.execute(
                text(
                    """
                    UPDATE iron_bank.underwritings AS uw
                    SET property_pending = (sl.home_status IS DISTINCT FROM 'FOR_SALE')
                    FROM zillow.scheduled_listings AS sl
                    WHERE uw.zpid = sl.zpid
                      AND uw.property_pending IS DISTINCT FROM (
                          sl.home_status IS DISTINCT FROM 'FOR_SALE'
                      )
                    """
                )
            )
            await self.db.commit()
            return result.rowcount
        except Exception:
            await self.db.rollback()
            raise

    def _update_model_fields(self, model, data: dict[str, Any]) -> None:
        for key, value in data.items():
            setattr(model, key, value)

    def _upsert_detail(
        self,
        underwriting: Underwriting,
        detail_data: dict[str, Any],
    ) -> None:
        if underwriting.detail is None:
            self.db.add(
                UnderwritingDetail(
                    underwriting_id=underwriting.id,
                    **detail_data,
                )
            )
            return

        self._update_model_fields(underwriting.detail, detail_data)

    def _upsert_taxes(
        self,
        underwriting: Underwriting,
        tax_data: dict[str, Any],
    ) -> None:
        if underwriting.taxes is None:
            self.db.add(
                UnderwritingTax(
                    underwriting_id=underwriting.id,
                    **tax_data,
                )
            )
            return

        self._update_model_fields(underwriting.taxes, tax_data)

    async def _upsert_children(
        self,
        *,
        model,
        underwriting_id: int,
        existing_rows,
        incoming: list[dict[str, Any]],
    ) -> None:
        """Diff a child collection against the incoming payload by primary key.

        Preserves row ids across updates (so the autoincrement sequence isn't
        churned on every edit): incoming items whose ``id`` matches an existing
        row are updated in place; items without a matching ``id`` are inserted
        with a fresh id; existing rows absent from the payload are deleted.

        A client-supplied ``id`` that does not belong to this underwriting is
        treated as a new insert — we never trust an arbitrary primary key from
        the request, we only reuse ids we already own for this row.

        ``sort_order`` is stamped from each item's position in the payload —
        the array order is the display order the client intends.
        """
        existing_by_id = {row.id: row for row in existing_rows}
        seen_ids: set[int] = set()

        for index, item in enumerate(incoming):
            fields = dict(item)
            fields["sort_order"] = index
            item_id = fields.pop("id", None)
            existing = existing_by_id.get(item_id) if item_id is not None else None
            if existing is not None:
                self._update_model_fields(existing, fields)
                seen_ids.add(item_id)
            else:
                self.db.add(model(underwriting_id=underwriting_id, **fields))

        for row_id, row in existing_by_id.items():
            if row_id not in seen_ids:
                await self.db.delete(row)
