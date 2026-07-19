from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.reference_data.models import EnumOption


class ReferenceDataRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_options(
        self,
        domain: str | None = None,
        set_codes: Sequence[str] | None = None,
        include_inactive: bool = False,
    ) -> list[EnumOption]:
        query = select(EnumOption)
        if domain is not None:
            query = query.where(EnumOption.domain == domain)
        if set_codes:
            query = query.where(EnumOption.set_code.in_(set_codes))
        if not include_inactive:
            query = query.where(EnumOption.is_active.is_(True))
        query = query.order_by(EnumOption.set_code, EnumOption.sort_order)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, option_id: int) -> EnumOption | None:
        result = await self.db.execute(
            select(EnumOption).where(EnumOption.id == option_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> EnumOption:
        option = EnumOption(**data)
        self.db.add(option)
        await self.db.commit()
        await self.db.refresh(option)
        return option

    async def update(self, option_id: int, data: dict) -> EnumOption | None:
        option = await self.get_by_id(option_id)
        if option is None:
            return None
        for key, value in data.items():
            setattr(option, key, value)
        await self.db.commit()
        await self.db.refresh(option)
        return option
