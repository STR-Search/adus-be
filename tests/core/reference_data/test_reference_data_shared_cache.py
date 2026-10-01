from types import SimpleNamespace

import pytest

from app.core.config import get_config
from app.core.reference_data import service as service_module
from app.core.reference_data.schemas import (
    CreateEnumOptionPayload,
    UpdateEnumOptionPayload,
)
from app.core.reference_data.service import ReferenceDataService


def _option(id, set_code, key, label, *, domain="iron_bank", metadata=None):
    return SimpleNamespace(
        id=id,
        domain=domain,
        set_code=set_code,
        key=key,
        label=label,
        sort_order=id,
        is_active=True,
        is_default=False,
        metadata_json=metadata,
        created_at=None,
        updated_at=None,
    )


class FakeReferenceDataRepository:
    """Counts list_options round trips; the options list can change under it."""

    def __init__(self, options):
        self.options = list(options)
        self.list_calls = []

    async def list_options(self, domain=None, set_codes=None, include_inactive=False):
        self.list_calls.append((domain, set_codes, include_inactive))
        return [
            option
            for option in self.options
            if (domain is None or option.domain == domain)
            and (not set_codes or option.set_code in set_codes)
            and (include_inactive or option.is_active)
        ]

    async def create(self, data):
        option = _option(
            len(self.options) + 1,
            data["set_code"],
            data["key"],
            data["label"],
            domain=data["domain"],
            metadata=data.get("metadata_json"),
        )
        self.options.append(option)
        return option

    async def update(self, option_id, data):
        option = next((o for o in self.options if o.id == option_id), None)
        if option is None:
            return None
        for key, value in data.items():
            setattr(option, key, value)
        return option


@pytest.fixture(autouse=True)
def _default_ttl(monkeypatch):
    # Pin the TTL so a local .env override can't change what these tests see.
    _set_ttl(monkeypatch, 300)


@pytest.fixture
def repository():
    return FakeReferenceDataRepository(
        [
            _option(1, "execution_type", "light_reno", "Light Renovation"),
            _option(2, "view_quality", "lake", "Lake View"),
            _option(3, "region", "north", "North", domain="markets"),
        ]
    )


@pytest.fixture
def clock(monkeypatch):
    """Controllable time.monotonic() for the service module only."""
    now = [1000.0]
    monkeypatch.setattr(
        service_module, "time", SimpleNamespace(monotonic=lambda: now[0])
    )
    return now


def _set_ttl(monkeypatch, seconds):
    monkeypatch.setattr(get_config(), "REFERENCE_DATA_CACHE_TTL_SECONDS", seconds)


@pytest.mark.asyncio
async def test_separate_service_instances_share_one_fetch(repository):
    first = await ReferenceDataService(repository).get_label_map(domain="iron_bank")
    second = await ReferenceDataService(repository).get_label_map(domain="iron_bank")

    assert len(repository.list_calls) == 1
    assert (
        first
        == second
        == {
            ("execution_type", "light_reno"): "Light Renovation",
            ("view_quality", "lake"): "Lake View",
        }
    )


@pytest.mark.asyncio
async def test_get_reference_data_reads_through_the_shared_cache(repository):
    await ReferenceDataService(repository).get_label_map(domain="iron_bank")
    result = await ReferenceDataService(repository).get_reference_data(
        domain="iron_bank"
    )

    assert len(repository.list_calls) == 1
    assert result.options["execution_type"][0].label == "Light Renovation"


@pytest.mark.asyncio
async def test_expired_entry_is_fetched_again(repository, clock):
    await ReferenceDataService(repository).get_label_map(domain="iron_bank")
    clock[0] += 299
    await ReferenceDataService(repository).get_label_map(domain="iron_bank")
    assert len(repository.list_calls) == 1

    clock[0] += 1
    await ReferenceDataService(repository).get_label_map(domain="iron_bank")
    assert len(repository.list_calls) == 2


@pytest.mark.asyncio
async def test_create_option_clears_the_shared_cache(repository):
    await ReferenceDataService(repository).get_label_map(domain="iron_bank")

    await ReferenceDataService(repository).create_option(
        CreateEnumOptionPayload(
            domain="iron_bank",
            set_code="view_quality",
            key="mountain",
            label="Mountain View",
        )
    )
    labels = await ReferenceDataService(repository).get_label_map(domain="iron_bank")

    assert len(repository.list_calls) == 2
    assert labels[("view_quality", "mountain")] == "Mountain View"


@pytest.mark.asyncio
async def test_update_option_clears_the_shared_cache(repository):
    await ReferenceDataService(repository).get_label_map(domain="iron_bank")

    await ReferenceDataService(repository).update_option(
        2, UpdateEnumOptionPayload(label="Lakefront")
    )
    labels = await ReferenceDataService(repository).get_label_map(domain="iron_bank")

    assert len(repository.list_calls) == 2
    assert labels[("view_quality", "lake")] == "Lakefront"


@pytest.mark.asyncio
async def test_update_of_a_missing_option_still_clears_the_shared_cache(repository):
    await ReferenceDataService(repository).get_label_map(domain="iron_bank")

    result = await ReferenceDataService(repository).update_option(
        999, UpdateEnumOptionPayload(label="Nope")
    )
    await ReferenceDataService(repository).get_label_map(domain="iron_bank")

    assert result is None
    assert len(repository.list_calls) == 2


@pytest.mark.asyncio
async def test_zero_ttl_disables_the_shared_cache(monkeypatch, repository):
    _set_ttl(monkeypatch, 0)

    for _ in range(3):
        await ReferenceDataService(repository).get_label_map(domain="iron_bank")

    assert len(repository.list_calls) == 3
    assert service_module._shared_cache is None


@pytest.mark.asyncio
async def test_validate_active_option_ignores_a_stale_shared_entry(repository):
    # Warm the shared entry validate_active_option would key on, then add the
    # option behind the cache's back (as another app instance would).
    await ReferenceDataService(repository).get_label_map(
        domain="iron_bank", set_codes=["view_quality"]
    )
    repository.options.append(_option(4, "view_quality", "mountain", "Mountain"))

    await ReferenceDataService(repository).validate_active_option(
        "iron_bank", "view_quality", "mountain"
    )

    assert len(repository.list_calls) == 2


@pytest.mark.asyncio
async def test_validate_active_option_rejects_an_option_deactivated_elsewhere(
    repository,
):
    await ReferenceDataService(repository).get_label_map(
        domain="iron_bank", set_codes=["view_quality"]
    )
    repository.options[1].is_active = False

    with pytest.raises(ValueError, match="Invalid view_quality: lake"):
        await ReferenceDataService(repository).validate_active_option(
            "iron_bank", "view_quality", "lake"
        )


@pytest.mark.asyncio
async def test_every_query_scope_is_served_from_one_table_fetch(repository):
    repository.options.append(
        _option(4, "view_quality", "retired", "Retired View", domain="iron_bank")
    )
    repository.options[-1].is_active = False
    service = ReferenceDataService(repository)

    iron_bank = await service.get_label_map(domain="iron_bank")
    markets = await service.get_label_map(domain="markets")
    views = await service.get_label_map(domain="iron_bank", set_codes=["view_quality"])
    everything = await service.get_label_map()
    unknown = await ReferenceDataService(repository).get_label_map(domain="typo")
    with_inactive = await service._list_shared_options(
        domain="iron_bank", set_codes=["view_quality"], include_inactive=True
    )

    # One whole-table fetch, inactive rows included, then filtered in memory.
    assert repository.list_calls == [(None, None, True)]
    assert iron_bank == {
        ("execution_type", "light_reno"): "Light Renovation",
        ("view_quality", "lake"): "Lake View",
    }
    assert markets == {("region", "north"): "North"}
    assert views == {("view_quality", "lake"): "Lake View"}
    assert everything == {**iron_bank, **markets}
    assert unknown == {}
    assert [option.key for option in with_inactive] == ["lake", "retired"]


@pytest.mark.asyncio
async def test_arbitrary_scopes_never_grow_the_shared_cache(repository):
    service = ReferenceDataService(repository)

    for i in range(50):
        await service.get_reference_data(domain=f"domain-{i}", set_codes=[f"s{i}"])
    await service.get_reference_data(set_codes=["view_quality", "execution_type"])
    await service.get_reference_data(set_codes=["execution_type", "view_quality"])

    _, snapshots = service_module._shared_cache
    assert len(repository.list_calls) == 1
    assert [option.id for option in snapshots] == [1, 2, 3]


@pytest.mark.asyncio
async def test_shared_entries_are_immutable_snapshots(repository):
    repository.options[0].metadata_json = {"tiers": ["low"]}
    service = ReferenceDataService(repository)

    first = await service.get_reference_data(domain="iron_bank")
    first.options["execution_type"][0].metadata["tiers"].append("mutated")
    repository.options[0].label = "Changed on the ORM row"
    second = await ReferenceDataService(repository).get_reference_data(
        domain="iron_bank"
    )

    _, snapshots = service_module._shared_cache
    assert isinstance(snapshots, tuple)
    assert second.options["execution_type"][0].label == "Light Renovation"
    assert second.options["execution_type"][0].metadata == {"tiers": ["low"]}
