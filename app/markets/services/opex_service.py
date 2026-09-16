from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.markets.enums import MarketStatus
from app.markets.models.opex import OpexByBedrooms, OpexBySize
from app.markets.repositories.market_repository import MarketRepository
from app.markets.repositories.opex_repository import OpexByBedroomsRepository, OpexBySizeRepository
from app.markets.schemas.opex import (
    OpexByBedroomsCreateSchema,
    OpexByBedroomsSchema,
    OpexByBedroomsUpdateSchema,
    OpexBySizeCreateSchema,
    OpexBySizeSchema,
    OpexBySizeUpdateSchema,
    OpexSeedResultSchema,
)


class OpexByBedroomsService:
    def __init__(self, repository: OpexByBedroomsRepository, market_repo: MarketRepository):
        self.repository = repository
        self.market_repo = market_repo

    async def _resolve_market_id(self, market_id: int | None, market_slug: str | None) -> int | None:
        if market_slug is not None:
            market = await self.market_repo.get_by_market_slug(market_slug)
            if market is None:
                raise ValueError(f"market_slug '{market_slug}' not found")
            return market.id
        return market_id

    async def _with_slug(self, record: OpexByBedrooms, slug_map: dict[int, str]) -> OpexByBedroomsSchema:
        schema = OpexByBedroomsSchema.model_validate(record)
        if record.market_id is not None:
            schema = schema.model_copy(update={"market_slug": slug_map.get(record.market_id)})
        return schema

    async def get_by_id(self, record_id: int) -> OpexByBedroomsSchema | None:
        record = await self.repository.get_by_id(record_id)
        if record is None:
            return None
        slug_map = await self.market_repo.get_slug_map(
            {record.market_id} if record.market_id is not None else set()
        )
        return await self._with_slug(record, slug_map)

    async def get_by_market_and_bedrooms(
        self,
        bedrooms: int,
        market_id: int | None = None,
        market_slug: str | None = None,
    ) -> OpexByBedroomsSchema | None:
        resolved_market_id = await self._resolve_market_id(market_id, market_slug)
        if resolved_market_id is None:
            return None
        record = await self.repository.get_by_market_and_bedrooms(resolved_market_id, bedrooms)
        if record is None:
            return None
        slug_map = await self.market_repo.get_slug_map({resolved_market_id})
        return await self._with_slug(record, slug_map)

    async def get_paginated(
        self,
        page: int,
        page_size: int,
        market_id: int | None = None,
        market_slug: str | None = None,
        bedrooms: int | None = None,
    ) -> tuple[list[OpexByBedroomsSchema], int, int]:
        resolved_market_id = await self._resolve_market_id(market_id, market_slug)
        items, total, pages = await self.repository.get_paginated(
            page=page,
            page_size=page_size,
            market_id=resolved_market_id,
            bedrooms=bedrooms,
        )
        slug_map = await self.market_repo.get_slug_map(
            {item.market_id for item in items if item.market_id is not None}
        )
        return [await self._with_slug(item, slug_map) for item in items], total, pages

    async def create(self, data: OpexByBedroomsCreateSchema) -> OpexByBedroomsSchema:
        market = await self._resolve_market_id(data.market_id, data.market_slug)
        payload = data.model_dump(exclude={"market_id", "market_slug"})
        payload["market_id"] = market
        record = await self.repository.create(payload)
        slug_map = await self.market_repo.get_slug_map(
            {record.market_id} if record.market_id is not None else set()
        )
        return await self._with_slug(record, slug_map)

    async def update(self, record_id: int, data: OpexByBedroomsUpdateSchema) -> OpexByBedroomsSchema | None:
        market = await self._resolve_market_id(data.market_id, data.market_slug)
        payload = data.model_dump(exclude={"market_id", "market_slug"}, exclude_unset=True)
        if market is not None or data.market_id is not None or data.market_slug is not None:
            payload["market_id"] = market
        record = await self.repository.update(record_id, payload)
        if record is None:
            return None
        slug_map = await self.market_repo.get_slug_map(
            {record.market_id} if record.market_id is not None else set()
        )
        return await self._with_slug(record, slug_map)

    async def delete(self, record_id: int) -> bool:
        return await self.repository.delete(record_id)


class OpexBySizeService:
    def __init__(self, repository: OpexBySizeRepository, market_repo: MarketRepository):
        self.repository = repository
        self.market_repo = market_repo

    async def _resolve_market_id(self, market_id: int | None, market_slug: str | None) -> int | None:
        if market_slug is not None:
            market = await self.market_repo.get_by_market_slug(market_slug)
            if market is None:
                raise ValueError(f"market_slug '{market_slug}' not found")
            return market.id
        return market_id

    async def _with_slug(self, record: OpexBySize, slug_map: dict[int, str]) -> OpexBySizeSchema:
        schema = OpexBySizeSchema.model_validate(record)
        if record.market_id is not None:
            schema = schema.model_copy(update={"market_slug": slug_map.get(record.market_id)})
        return schema

    async def get_by_id(self, record_id: int) -> OpexBySizeSchema | None:
        record = await self.repository.get_by_id(record_id)
        if record is None:
            return None
        slug_map = await self.market_repo.get_slug_map(
            {record.market_id} if record.market_id is not None else set()
        )
        return await self._with_slug(record, slug_map)

    async def get_by_market_and_sqft(
        self,
        sqft: int,
        market_id: int | None = None,
        market_slug: str | None = None,
    ) -> OpexBySizeSchema | None:
        resolved_market_id = await self._resolve_market_id(market_id, market_slug)
        if resolved_market_id is None:
            return None
        record = await self.repository.get_by_market_and_sqft(resolved_market_id, sqft)
        if record is None:
            return None
        slug_map = await self.market_repo.get_slug_map({resolved_market_id})
        return await self._with_slug(record, slug_map)

    async def get_paginated(
        self,
        page: int,
        page_size: int,
        market_id: int | None = None,
        market_slug: str | None = None,
        sqft: int | None = None,
    ) -> tuple[list[OpexBySizeSchema], int, int]:
        resolved_market_id = await self._resolve_market_id(market_id, market_slug)
        items, total, pages = await self.repository.get_paginated(
            page=page,
            page_size=page_size,
            market_id=resolved_market_id,
            sqft=sqft,
        )
        slug_map = await self.market_repo.get_slug_map(
            {item.market_id for item in items if item.market_id is not None}
        )
        return [await self._with_slug(item, slug_map) for item in items], total, pages

    async def create(self, data: OpexBySizeCreateSchema) -> OpexBySizeSchema:
        market = await self._resolve_market_id(data.market_id, data.market_slug)
        payload = data.model_dump(exclude={"market_id", "market_slug"})
        payload["market_id"] = market
        record = await self.repository.create(payload)
        slug_map = await self.market_repo.get_slug_map(
            {record.market_id} if record.market_id is not None else set()
        )
        return await self._with_slug(record, slug_map)

    async def update(self, record_id: int, data: OpexBySizeUpdateSchema) -> OpexBySizeSchema | None:
        market = await self._resolve_market_id(data.market_id, data.market_slug)
        payload = data.model_dump(exclude={"market_id", "market_slug"}, exclude_unset=True)
        if market is not None or data.market_id is not None or data.market_slug is not None:
            payload["market_id"] = market
        record = await self.repository.update(record_id, payload)
        if record is None:
            return None
        slug_map = await self.market_repo.get_slug_map(
            {record.market_id} if record.market_id is not None else set()
        )
        return await self._with_slug(record, slug_map)

    async def delete(self, record_id: int) -> bool:
        return await self.repository.delete(record_id)


class OpexSeedError(Exception):
    """Base for the seed-from-lookalike refusals the controller maps to 4xx."""


class OpexSeedSameMarketError(OpexSeedError):
    def __init__(self, market_id: int):
        super().__init__(f"Market {market_id} cannot be seeded from itself")
        self.market_id = market_id


class OpexSeedTargetNotExploratoryError(OpexSeedError):
    """The target market is not exploratory, so seeding would clobber real data.

    ``market_status`` is free-text varchar (see ``app.markets.enums``), so the
    check is a normalized string compare rather than an enum coercion -- a row
    seeded from CSV with stray case or whitespace still matches.
    """

    def __init__(self, market_id: int, market_status: str | None):
        super().__init__(
            f"Market {market_id} has status '{market_status}'; opex can only be "
            f"seeded into an exploratory market"
        )
        self.market_id = market_id
        self.market_status = market_status


class OpexSeedSourceEmptyError(OpexSeedError):
    def __init__(self, market_id: int, empty_tables: list[str]):
        super().__init__(
            f"Lookalike market {market_id} has no rows in "
            f"{', '.join(empty_tables)}; nothing to seed from"
        )
        self.market_id = market_id
        self.empty_tables = empty_tables


class OpexSeedTargetAlreadySeededError(OpexSeedError):
    """The target already holds opex rows.

    Both opex tables carry a partial unique index on (market_id, key) scoped to
    live rows, so inserting over an existing set would fail at flush anyway.
    Refusing up front turns that IntegrityError into an answer the caller can
    act on, and keeps the endpoint from being a silent overwrite of numbers an
    analyst may have already tuned.
    """

    def __init__(self, market_id: int, tables: list[str]):
        super().__init__(
            f"Rows are already there for this market in {', '.join(tables)}, "
            f"go ahead and edit them if needed."
        )
        self.market_id = market_id
        self.tables = tables


class OpexSeedService:
    """Copies one market's opex rows onto an exploratory market.

    A one-time snapshot, not a live link: the rows become the target's own and
    are edited through the ordinary opex CRUD afterwards. Both tables are
    written in a single transaction -- hence the session here and the
    non-committing ``insert_all`` on the repositories -- so a market never ends
    up with bedrooms rows but no size rows.
    """

    # Server-assigned on insert (id) or meaningless to copy (deleted_at: source
    # rows are all live by construction). Every other column is carried across
    # by name, so a column added to either opex table is seeded without this
    # service needing to know about it.
    SKIP_COLUMNS = frozenset({"id", "deleted_at"})

    def __init__(
        self,
        db: AsyncSession,
        bedrooms_repo: OpexByBedroomsRepository,
        size_repo: OpexBySizeRepository,
        market_repo: MarketRepository,
    ):
        self.db = db
        self.bedrooms_repo = bedrooms_repo
        self.size_repo = size_repo
        self.market_repo = market_repo

    def _clone_rows(
        self, records: Sequence[OpexByBedrooms | OpexBySize], target_market_id: int
    ) -> list[dict]:
        return [
            {
                column.name: getattr(record, column.name)
                for column in record.__table__.columns
                if column.name not in self.SKIP_COLUMNS
            }
            | {"market_id": target_market_id}
            for record in records
        ]

    async def seed_from_lookalike(
        self, target_market_id: int, source_market_id: int
    ) -> OpexSeedResultSchema:
        if target_market_id == source_market_id:
            raise OpexSeedSameMarketError(target_market_id)

        target = await self.market_repo.get_by_id(target_market_id)
        if target is None:
            raise ValueError(f"market_id {target_market_id} not found")

        status = (target.market_status or "").strip().lower()
        if status != MarketStatus.EXPLORATORY:
            raise OpexSeedTargetNotExploratoryError(target_market_id, target.market_status)

        source = await self.market_repo.get_by_id(source_market_id)
        if source is None:
            raise ValueError(f"market_id {source_market_id} not found")

        # Refuse before writing anything: the two checks below are what make
        # this endpoint safe to retry.
        existing_tables = [
            name
            for name, rows in (
                ("opex_by_bedrooms", await self.bedrooms_repo.get_all_by_market(target_market_id)),
                ("opex_by_size", await self.size_repo.get_all_by_market(target_market_id)),
            )
            if rows
        ]
        if existing_tables:
            raise OpexSeedTargetAlreadySeededError(target_market_id, existing_tables)

        source_bedrooms = await self.bedrooms_repo.get_all_by_market(source_market_id)
        source_size = await self.size_repo.get_all_by_market(source_market_id)
        empty_tables = [
            name
            for name, rows in (
                ("opex_by_bedrooms", source_bedrooms),
                ("opex_by_size", source_size),
            )
            if not rows
        ]
        # Both or neither. A source missing one table would leave the target
        # half-seeded, which reads as success to the caller but breaks the
        # underwriting payload builders that expect both sets.
        if empty_tables:
            raise OpexSeedSourceEmptyError(source_market_id, empty_tables)

        try:
            bedrooms_created = await self.bedrooms_repo.insert_all(
                self._clone_rows(source_bedrooms, target_market_id)
            )
            size_created = await self.size_repo.insert_all(
                self._clone_rows(source_size, target_market_id)
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        logger.info(
            "opex.seed_from_lookalike",
            target_market_id=target_market_id,
            source_market_id=source_market_id,
            bedrooms_created=len(bedrooms_created),
            size_created=len(size_created),
        )
        return OpexSeedResultSchema(
            target_market_id=target_market_id,
            source_market_id=source_market_id,
            bedrooms_created=len(bedrooms_created),
            size_created=len(size_created),
        )
