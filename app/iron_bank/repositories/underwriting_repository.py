import math
from decimal import Decimal
from typing import Any

from sqlalchemy import bindparam, delete, func, select, text
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
        source: str | None = None,
        min_purchase_price: Decimal | None = None,
        max_purchase_price: Decimal | None = None,
        min_total_oop: Decimal | None = None,
        max_total_oop: Decimal | None = None,
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
        if source is not None:
            query = query.where(Underwriting.source == source)
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

    async def get_user_names(self, user_ids: set[int]) -> dict[int, str]:
        """Display names for analyst/approver ids. Textual query on users.users
        keeps the iron_bank domain from importing the users domain's models."""
        if not user_ids:
            return {}
        result = await self.db.execute(
            text(
                "SELECT id, first_name, last_name FROM users.users "
                "WHERE id IN :ids"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": list(user_ids)},
        )
        return {
            row.id: name
            for row in result
            if (name := f"{row.first_name or ''} {row.last_name or ''}".strip())
        }

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

            for item in optimization_items or []:
                self.db.add(
                    UnderwritingOptimizationItem(
                        underwriting_id=underwriting.id,
                        **item,
                    )
                )

            for expense in operating_expenses or []:
                self.db.add(
                    UnderwritingOperatingExpense(
                        underwriting_id=underwriting.id,
                        **expense,
                    )
                )

            for comp in comp_set or []:
                self.db.add(
                    UnderwritingCompSet(
                        underwriting_id=underwriting.id,
                        **comp,
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
                await self._replace_optimization_items(
                    underwriting_id, optimization_items
                )
            if operating_expenses is not None:
                await self._replace_operating_expenses(
                    underwriting_id, operating_expenses
                )
            if comp_set is not None:
                await self._replace_comp_set(underwriting_id, comp_set)

            await self.db.commit()
            await self.db.refresh(underwriting)
            return underwriting
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

    async def _replace_optimization_items(
        self,
        underwriting_id: int,
        items: list[dict[str, Any]],
    ) -> None:
        await self.db.execute(
            delete(UnderwritingOptimizationItem).where(
                UnderwritingOptimizationItem.underwriting_id == underwriting_id
            )
        )
        for item in items:
            self.db.add(
                UnderwritingOptimizationItem(
                    underwriting_id=underwriting_id,
                    **item,
                )
            )

    async def _replace_operating_expenses(
        self,
        underwriting_id: int,
        expenses: list[dict[str, Any]],
    ) -> None:
        await self.db.execute(
            delete(UnderwritingOperatingExpense).where(
                UnderwritingOperatingExpense.underwriting_id == underwriting_id
            )
        )
        for expense in expenses:
            self.db.add(
                UnderwritingOperatingExpense(
                    underwriting_id=underwriting_id,
                    **expense,
                )
            )

    async def _replace_comp_set(
        self,
        underwriting_id: int,
        comp_set: list[dict[str, Any]],
    ) -> None:
        await self.db.execute(
            delete(UnderwritingCompSet).where(
                UnderwritingCompSet.underwriting_id == underwriting_id
            )
        )
        for comp in comp_set:
            self.db.add(
                UnderwritingCompSet(
                    underwriting_id=underwriting_id,
                    **comp,
                )
            )
