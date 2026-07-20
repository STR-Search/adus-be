from collections.abc import Sequence

from app.core.reference_data.models import EnumOption
from app.core.reference_data.repository import ReferenceDataRepository
from app.core.reference_data.schemas import (
    CreateEnumOptionPayload,
    EnumOptionRead,
    ReferenceDataOption,
    ReferenceDataResult,
    UpdateEnumOptionPayload,
)


class ReferenceDataService:
    def __init__(self, repository: ReferenceDataRepository):
        self.repository = repository
        # Per-request cache: fetched option rows keyed by the query that
        # produced them. Invalidated on any create/update.
        self._cache: dict[tuple, list[EnumOption]] = {}

    @staticmethod
    def _cache_key(
        domain: str | None,
        set_codes: Sequence[str] | None,
        include_inactive: bool,
    ) -> tuple:
        return (domain, tuple(set_codes) if set_codes else None, include_inactive)

    async def _list_options(
        self,
        domain: str | None = None,
        set_codes: Sequence[str] | None = None,
        include_inactive: bool = False,
    ) -> list[EnumOption]:
        key = self._cache_key(domain, set_codes, include_inactive)
        if key not in self._cache:
            self._cache[key] = await self.repository.list_options(
                domain=domain,
                set_codes=set_codes,
                include_inactive=include_inactive,
            )
        return self._cache[key]

    @staticmethod
    def _to_option(option: EnumOption) -> ReferenceDataOption:
        return ReferenceDataOption(
            key=option.key,
            label=option.label,
            sort_order=option.sort_order,
            is_active=option.is_active,
            is_default=option.is_default,
            metadata=option.metadata_json,
        )

    @staticmethod
    def _to_read(option: EnumOption) -> EnumOptionRead:
        return EnumOptionRead(
            id=option.id,
            domain=option.domain,
            set_code=option.set_code,
            key=option.key,
            label=option.label,
            sort_order=option.sort_order,
            is_active=option.is_active,
            is_default=option.is_default,
            metadata=option.metadata_json,
            created_at=option.created_at,
            updated_at=option.updated_at,
        )

    async def get_reference_data(
        self,
        domain: str | None = None,
        set_codes: Sequence[str] | None = None,
    ) -> ReferenceDataResult:
        options = await self._list_options(domain=domain, set_codes=set_codes)
        grouped: dict[str, list[ReferenceDataOption]] = {}
        for option in options:
            grouped.setdefault(option.set_code, []).append(self._to_option(option))
        return ReferenceDataResult(options=grouped)

    async def get_set_codes(
        self,
        domain: str | None = None,
    ) -> list[str]:
        """List the distinct ``set_code`` values available for a domain."""
        return await self.repository.list_set_codes(domain=domain)

    async def get_label_map(
        self,
        domain: str | None = None,
        set_codes: Sequence[str] | None = None,
    ) -> dict[tuple[str, str], str]:
        """Map ``(set_code, key)`` → ``label`` for the requested scope."""
        options = await self._list_options(domain=domain, set_codes=set_codes)
        return {(option.set_code, option.key): option.label for option in options}

    async def validate_active_option(
        self,
        domain: str | None,
        set_code: str,
        key: str | None,
    ) -> None:
        """Raise ``ValueError`` unless ``key`` is an active option in the set.

        A ``None`` key is a no-op (the tag is simply unset).
        """
        if key is None:
            return
        options = await self._list_options(domain=domain, set_codes=[set_code])
        if not any(option.key == key for option in options):
            raise ValueError(f"Invalid {set_code}: {key}")

    async def create_option(
        self, payload: CreateEnumOptionPayload
    ) -> EnumOptionRead:
        data = payload.model_dump()
        data["metadata_json"] = data.pop("metadata")
        option = await self.repository.create(data)
        self._cache.clear()
        return self._to_read(option)

    async def update_option(
        self, option_id: int, payload: UpdateEnumOptionPayload
    ) -> EnumOptionRead | None:
        data = payload.model_dump(exclude_unset=True)
        if "metadata" in data:
            data["metadata_json"] = data.pop("metadata")
        option = await self.repository.update(option_id, data)
        self._cache.clear()
        if option is None:
            return None
        return self._to_read(option)
