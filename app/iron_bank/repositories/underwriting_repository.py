import math
from typing import Any

from sqlalchemy import func, select
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
            .order_by(Underwriting.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_zpid(self, zpid: str) -> Underwriting | None:
        result = await self.db.execute(
            select(Underwriting)
            .where(Underwriting.zpid == zpid)
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
