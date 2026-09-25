import copy
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.config import get_config
from app.core.reference_data.models import EnumOption
from app.core.reference_data.repository import ReferenceDataRepository
from app.core.reference_data.schemas import (
    CreateEnumOptionPayload,
    EnumOptionRead,
    ReferenceDataOption,
    ReferenceDataResult,
    UpdateEnumOptionPayload,
)


@dataclass(frozen=True, slots=True)
class _OptionSnapshot:
    """Session-free copy of an ``EnumOption`` row, safe to share across requests.

    ORM instances are bound to the request's session, so the shared cache only
    ever holds these.
    """

    id: int
    domain: str
    set_code: str
    key: str
    label: str
    sort_order: int
    is_active: bool
    is_default: bool
    metadata_json: dict[str, Any] | None
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_model(cls, option: EnumOption) -> "_OptionSnapshot":
        return cls(
            id=option.id,
            domain=option.domain,
            set_code=option.set_code,
            key=option.key,
            label=option.label,
            sort_order=option.sort_order,
            is_active=option.is_active,
            is_default=option.is_default,
            # Deep-copied so the snapshot shares no mutable state with the row.
            metadata_json=copy.deepcopy(option.metadata_json),
            created_at=option.created_at,
            updated_at=option.updated_at,
        )


# Process-level cache shared by every ReferenceDataService instance: the whole
# reference.enum_options table (inactive rows included) as snapshots, with the
# time.monotonic() it was fetched at. Reads filter it in memory, so it is always
# a single entry however callers scope their queries (GET /reference-data takes
# client-supplied domain/sets). Expires after REFERENCE_DATA_CACHE_TTL_SECONDS;
# 0 disables it. No lock: two concurrent misses may both fetch, which is
# harmless.
#
# Known trade-off: create/update only clears the cache of the app instance that
# served the write. With several instances, the others keep serving stale labels
# for up to the TTL. Cross-instance invalidation (Redis pub/sub) is a planned
# follow-up, intentionally out of scope for now.
_shared_cache: tuple[float, tuple[_OptionSnapshot, ...]] | None = None


def clear_shared_cache() -> None:
    global _shared_cache
    _shared_cache = None


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

    async def _list_shared_options(
        self,
        domain: str | None = None,
        set_codes: Sequence[str] | None = None,
        include_inactive: bool = False,
    ) -> tuple[_OptionSnapshot, ...]:
        """Read-only option snapshots via the process-level TTL cache.

        Filtered in memory from the cached table, mirroring the repository's
        ``list_options`` filters; the table's ``(set_code, sort_order)`` order
        carries through. With the TTL at 0 this falls back to the per-instance
        cache.
        """
        ttl = get_config().REFERENCE_DATA_CACHE_TTL_SECONDS
        if ttl <= 0:
            options = await self._list_options(
                domain=domain, set_codes=set_codes, include_inactive=include_inactive
            )
            return tuple(_OptionSnapshot.from_model(option) for option in options)
        wanted_sets = set(set_codes) if set_codes else None
        return tuple(
            option
            for option in await self._shared_table(ttl)
            if (domain is None or option.domain == domain)
            and (wanted_sets is None or option.set_code in wanted_sets)
            and (include_inactive or option.is_active)
        )

    async def _shared_table(self, ttl: int) -> tuple[_OptionSnapshot, ...]:
        global _shared_cache
        if _shared_cache is not None and time.monotonic() - _shared_cache[0] < ttl:
            return _shared_cache[1]
        options = await self.repository.list_options(include_inactive=True)
        snapshots = tuple(_OptionSnapshot.from_model(option) for option in options)
        _shared_cache = (time.monotonic(), snapshots)
        return snapshots

    def _clear_caches(self) -> None:
        self._cache.clear()
        clear_shared_cache()

    @staticmethod
    def _to_option(option: _OptionSnapshot) -> ReferenceDataOption:
        return ReferenceDataOption(
            key=option.key,
            label=option.label,
            sort_order=option.sort_order,
            is_active=option.is_active,
            is_default=option.is_default,
            metadata=copy.deepcopy(option.metadata_json),
        )

    @staticmethod
    def _to_read(option: _OptionSnapshot) -> EnumOptionRead:
        return EnumOptionRead(
            id=option.id,
            domain=option.domain,
            set_code=option.set_code,
            key=option.key,
            label=option.label,
            sort_order=option.sort_order,
            is_active=option.is_active,
            is_default=option.is_default,
            metadata=copy.deepcopy(option.metadata_json),
            created_at=option.created_at,
            updated_at=option.updated_at,
        )

    async def get_reference_data(
        self,
        domain: str | None = None,
        set_codes: Sequence[str] | None = None,
    ) -> ReferenceDataResult:
        options = await self._list_shared_options(domain=domain, set_codes=set_codes)
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
        options = await self._list_shared_options(domain=domain, set_codes=set_codes)
        return {(option.set_code, option.key): option.label for option in options}

    async def validate_active_option(
        self,
        domain: str | None,
        set_code: str,
        key: str | None,
    ) -> None:
        """Raise ``ValueError`` unless ``key`` is an active option in the set.

        A ``None`` key is a no-op (the tag is simply unset). Guards writes, so it
        reads through the per-instance cache only, never the shared one: another
        instance's stale entry must not admit a deactivated option or reject a
        newly created one.
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
        # Cleared only after the repository has committed, so a concurrent read
        # can't re-cache pre-commit data.
        self._clear_caches()
        return self._to_read(_OptionSnapshot.from_model(option))

    async def update_option(
        self, option_id: int, payload: UpdateEnumOptionPayload
    ) -> EnumOptionRead | None:
        data = payload.model_dump(exclude_unset=True)
        if "metadata" in data:
            data["metadata_json"] = data.pop("metadata")
        option = await self.repository.update(option_id, data)
        self._clear_caches()
        if option is None:
            return None
        return self._to_read(_OptionSnapshot.from_model(option))
