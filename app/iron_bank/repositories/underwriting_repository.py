import math
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    ) -> tuple[list[Underwriting], int, int]:
        """Returns (items, total, pages) ordered by newest underwriting first."""
        query = select(Underwriting)
        if zpid is not None:
            query = query.where(Underwriting.zpid == zpid)
        if market_id is not None:
            query = query.where(Underwriting.market_id == market_id)

        total: int = (
            await self.db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()
        pages = math.ceil(total / page_size) if page_size > 0 else 0

        result = await self.db.execute(
            query.options(
                selectinload(Underwriting.detail),
                selectinload(Underwriting.taxes),
                selectinload(Underwriting.optimization_items),
                selectinload(Underwriting.operating_expenses),
                selectinload(Underwriting.comp_set),
            )
            .order_by(Underwriting.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(result.scalars().all())
        return items, total, pages

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
