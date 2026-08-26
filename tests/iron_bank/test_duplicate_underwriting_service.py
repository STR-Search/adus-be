import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import Null

from app.iron_bank.enums import DealStatus, UnderwritingSource
from app.iron_bank.models import (
    Underwriting,
    UnderwritingCompSet,
    UnderwritingDetail,
    UnderwritingOperatingExpense,
    UnderwritingOptimizationItem,
    UnderwritingTax,
)
from app.iron_bank.services.duplicate_underwriting_service import (
    _UNDERWRITING_NON_COPYABLE,
    DuplicateUnderwritingService,
)

SERIES_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
POISON_SERIES_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")

# Pinned so adding a column to Underwriting fails here rather than silently
# inheriting the copy-by-default behaviour. When this fails: decide whether the
# new column should survive duplication, update _UNDERWRITING_NON_COPYABLE if
# not, then add the name here.
_EXPECTED_UNDERWRITING_COLUMNS = frozenset(
    {
        "add_inground_pool", "analyst_id", "approver_id", "arv", "bathrooms",
        "bedrooms", "budget_to_pp", "can_support_cohost", "cash_flow_quality",
        "city", "copied_from_id", "core_value_driver", "created_at",
        "days_on_market", "deal_added", "deal_approved", "deal_complexity",
        "deal_pitch", "deal_score", "deal_status", "deal_submitted",
        "execution_type", "existing_airbnb", "furnished", "h_cash_on_cash",
        "high_cash_on_cash", "high_gross_revenue", "id", "is_automated",
        "l_cash_on_cash", "listing_url", "loom_vid", "low_cash_on_cash",
        "low_gross_revenue", "luxury", "m_cash_on_cash", "market_id",
        "market_type", "mid_gross_revenue", "new_construction", "note",
        "offer_competitiveness", "owner_id", "pool_type",
        "primary_guest_avatar", "property_address", "property_pending", "prr",
        "purchase_price", "regulatory_clarity", "remote", "renovation_level",
        "seasonality", "series_id", "sheet_number", "sleep_capacity", "source",
        "state", "street", "survey", "tax_efficient", "total_oop", "turnkey",
        "updated_at", "version", "video_walkthrough", "view_quality",
        "waterfront", "zpid",
    }
)


class FakeRepository:
    """Stands in for UnderwritingRepository — no DB, records what it was given."""

    def __init__(
        self, source, *, conflict_versions=frozenset(), poison_source_on_rollback=False
    ):
        self.source = source
        self.conflict_versions = conflict_versions
        self.poison_source_on_rollback = poison_source_on_rollback
        self.created = []
        self.next_id = 900
        self.version_reads = 0
        # Versions a concurrent writer took from under us. A collision means the
        # row now exists, so the next max() read must see it — otherwise the
        # retry would loop on the same number forever, which the real DB never
        # does.
        self._claimed_by_others = set()

    async def get_by_id(self, underwriting_id):
        if self.source is None or self.source.id != underwriting_id:
            return None
        return self.source

    async def get_next_version_for_series(self, series_id):
        self.version_reads += 1
        versions = [
            call["underwriting_data"]["version"]
            for call in self.created
            if call["underwriting_data"]["series_id"] == series_id
        ]
        base = [self.source.version] if self.source is not None else [0]
        return max(base + versions + list(self._claimed_by_others)) + 1

    async def create(self, underwriting_data, **children):
        version = underwriting_data["version"]
        if version in self.conflict_versions:
            self._claimed_by_others.add(version)
            if self.poison_source_on_rollback and self.source is not None:
                # The real repository rolls the session back here, and
                # Session.rollback() expires every loaded ORM instance — in
                # production, re-reading source.id would then lazy-load
                # synchronously and raise MissingGreenlet. A detached instance
                # can't reproduce that, so stand in for it with values that are
                # obviously wrong: any read of `source` after this point shows
                # up in the assertions.
                self.source.id = -1
                self.source.series_id = POISON_SERIES_ID
            # Mirrors the shape asyncpg surfaces: the constraint name appears in
            # the wrapped original error.
            raise IntegrityError(
                "INSERT INTO iron_bank.underwritings",
                {},
                Exception(
                    'duplicate key value violates unique constraint '
                    '"uq_underwritings_series_version"'
                ),
            )
        self.created.append(
            {"underwriting_data": dict(underwriting_data), **children}
        )
        self.next_id += 1
        return Underwriting(
            id=self.next_id,
            series_id=underwriting_data["series_id"],
            version=version,
        )


def _source_underwriting(**overrides):
    """A source row with every copyable column carrying a distinctive value."""
    source = Underwriting(
        id=42,
        series_id=SERIES_ID,
        version=0,
        copied_from_id=None,
        zpid="26110417",
        market_id=7,
        analyst_id=11,
        approver_id=12,
        owner_id=13,
        deal_status=DealStatus.CLIENT_UNDER_CONTRACT.value,
        is_automated=True,
        source=UnderwritingSource.LEGACY_SHEET.value,
        sheet_number=314,
        deal_score=88,
        property_address="1 Elm St",
        street="1 Elm St",
        city="Austin",
        state="TX",
        bedrooms=4,
        purchase_price=750000,
        total_oop=210000,
        l_cash_on_cash="0.0812",
        market_type=["beach", "lake"],
        execution_type="turnkey",
        listing_url="https://www.zillow.com/homedetails/26110417_zpid/",
        loom_vid="https://loom.example/abc",
        video_walkthrough="https://video.example/abc",
        survey="https://survey.example/abc",
        deal_pitch="A compelling pitch",
        note="Analyst note",
        turnkey=True,
        waterfront=True,
    )
    for key, value in overrides.items():
        setattr(source, key, value)
    return source


def _with_children(source):
    source.detail = UnderwritingDetail(
        id=501,
        underwriting_id=source.id,
        purchase_details={"price": 750000},
        zillow_property={"zpid": "26110417"},
        analyst_notes="detail notes",
        construction_and_design_notes="design notes",
    )
    source.taxes = UnderwritingTax(
        id=601, underwriting_id=source.id, tax_savings=12345, tax_rate_pct="0.0210"
    )
    source.optimization_items = [
        UnderwritingOptimizationItem(
            id=701, underwriting_id=source.id, category="Pool",
            total_price=60000, sort_order=0,
        ),
        UnderwritingOptimizationItem(
            id=702, underwriting_id=source.id, category="Deck",
            total_price=15000, sort_order=1,
        ),
    ]
    source.operating_expenses = [
        UnderwritingOperatingExpense(
            id=801, underwriting_id=source.id,
            expense_name="Internet", monthly_amount=100, sort_order=0,
        ),
    ]
    source.comp_set = [
        UnderwritingCompSet(
            id=901, underwriting_id=source.id,
            listing_url="https://airbnb.example/1", revenue=103200,
            bedrooms=4, sleeps=10, is_favourite=True, sort_order=0,
        ),
    ]
    return source


def _empty_children(source):
    source.detail = None
    source.taxes = None
    source.optimization_items = []
    source.operating_expenses = []
    source.comp_set = []
    return source


def test_underwriting_column_set_is_pinned():
    assert set(Underwriting.__table__.columns.keys()) == (
        _EXPECTED_UNDERWRITING_COLUMNS
    ), (
        "Underwriting's columns changed. Decide whether each new column should "
        "survive duplication (update _UNDERWRITING_NON_COPYABLE if not), then "
        "update this pin."
    )


@pytest.mark.asyncio
async def test_copies_every_column_outside_the_non_copyable_set():
    source = _empty_children(_source_underwriting())
    repository = FakeRepository(source)
    service = DuplicateUnderwritingService(repository)

    await service.duplicate(underwriting_id=42, current_user_id=99)

    created = repository.created[0]["underwriting_data"]
    copyable = _EXPECTED_UNDERWRITING_COLUMNS - _UNDERWRITING_NON_COPYABLE
    for name in copyable:
        assert created[name] == getattr(source, name), f"{name} was not copied"


@pytest.mark.asyncio
async def test_resets_workflow_provenance_and_narrative_fields():
    source = _empty_children(_source_underwriting())
    repository = FakeRepository(source)
    service = DuplicateUnderwritingService(repository)

    await service.duplicate(underwriting_id=42, current_user_id=99)
    created = repository.created[0]["underwriting_data"]

    # A terminal status would leave the copy with no legal transitions.
    assert created["deal_status"] == DealStatus.TEMPLATE_GENERATED.value
    assert created["source"] == UnderwritingSource.ADUS.value
    assert created["sheet_number"] is None
    assert created["deal_score"] is None
    for field in ("deal_pitch", "note", "loom_vid", "video_walkthrough", "survey"):
        assert field not in created, f"{field} should not be carried over"
    for field in ("id", "created_at", "updated_at", "deal_added",
                  "deal_submitted", "deal_approved"):
        assert field not in created


@pytest.mark.parametrize("is_automated", [True, False])
@pytest.mark.asyncio
async def test_preserves_the_zillow_hydration_path(is_automated):
    """is_automated selects a read path, so it must survive duplication.

    Automated rows carry a zpid and NO uw_details.zillow_property (the automated
    builder never writes one); non-automated rows carry the snapshot instead.
    Forcing the copy to False would send a copy of an automated row down the
    stored-snapshot branch of GetUnderwritingService.get_edit_context, where it
    would find NULL and render no zillow data at all.
    """
    source = _empty_children(_source_underwriting(is_automated=is_automated))
    repository = FakeRepository(source)
    service = DuplicateUnderwritingService(repository)

    await service.duplicate(underwriting_id=42, current_user_id=99)

    assert repository.created[0]["underwriting_data"]["is_automated"] is is_automated


@pytest.mark.asyncio
async def test_assigns_duplicator_as_analyst_and_keeps_owner():
    source = _empty_children(_source_underwriting())
    repository = FakeRepository(source)
    service = DuplicateUnderwritingService(repository)

    await service.duplicate(underwriting_id=42, current_user_id=99)
    created = repository.created[0]["underwriting_data"]

    assert created["analyst_id"] == 99
    assert created["approver_id"] is None
    # Ownership is a market-level fact and survives the fork.
    assert created["owner_id"] == 13


@pytest.mark.asyncio
async def test_joins_source_series_at_next_version():
    source = _empty_children(_source_underwriting(version=2))
    repository = FakeRepository(source)
    service = DuplicateUnderwritingService(repository)

    result = await service.duplicate(underwriting_id=42, current_user_id=99)
    created = repository.created[0]["underwriting_data"]

    assert created["series_id"] == SERIES_ID
    assert created["version"] == 3
    assert created["copied_from_id"] == 42
    assert result.series_id == SERIES_ID
    assert result.version == 3
    assert result.copied_from_id == 42
    assert result.underwriting_id == repository.next_id


@pytest.mark.asyncio
async def test_duplicate_of_a_duplicate_points_at_the_copy_not_the_original():
    copy = _empty_children(
        _source_underwriting(id=77, version=1, copied_from_id=42)
    )
    repository = FakeRepository(copy)
    service = DuplicateUnderwritingService(repository)

    await service.duplicate(underwriting_id=77, current_user_id=99)
    created = repository.created[0]["underwriting_data"]

    assert created["copied_from_id"] == 77
    assert created["series_id"] == SERIES_ID
    assert created["version"] == 2


@pytest.mark.asyncio
async def test_copies_children_without_ids_and_preserves_order():
    source = _with_children(_source_underwriting())
    repository = FakeRepository(source)
    service = DuplicateUnderwritingService(repository)

    await service.duplicate(underwriting_id=42, current_user_id=99)
    call = repository.created[0]

    assert call["detail_data"]["purchase_details"] == {"price": 750000}
    assert call["detail_data"]["zillow_property"] == {"zpid": "26110417"}
    assert call["detail_data"]["construction_and_design_notes"] == "design notes"
    assert "id" not in call["detail_data"]
    assert "underwriting_id" not in call["detail_data"]

    assert call["tax_data"]["tax_savings"] == 12345
    assert "id" not in call["tax_data"]

    # sort_order is stripped: the repository re-stamps it from list position,
    # and leaving it in would collide with its positional keyword.
    assert [item["category"] for item in call["optimization_items"]] == [
        "Pool",
        "Deck",
    ]
    for item in call["optimization_items"]:
        assert "id" not in item and "sort_order" not in item

    assert call["operating_expenses"][0]["expense_name"] == "Internet"
    assert call["comp_set"][0]["is_favourite"] is True
    assert call["comp_set"][0]["revenue"] == 103200


@pytest.mark.asyncio
async def test_handles_a_source_with_no_children():
    source = _empty_children(_source_underwriting())
    repository = FakeRepository(source)
    service = DuplicateUnderwritingService(repository)

    await service.duplicate(underwriting_id=42, current_user_id=99)
    call = repository.created[0]

    assert call["detail_data"] is None
    assert call["tax_data"] is None
    assert call["optimization_items"] == []
    assert call["comp_set"] == []


@pytest.mark.asyncio
async def test_retries_on_a_series_version_conflict():
    source = _empty_children(_source_underwriting(version=0))
    # Another duplicate of the same series claims version 1 first.
    repository = FakeRepository(source, conflict_versions={1})
    service = DuplicateUnderwritingService(repository)

    result = await service.duplicate(underwriting_id=42, current_user_id=99)

    assert result.version == 2
    assert repository.version_reads == 2


@pytest.mark.asyncio
async def test_retry_survives_the_rollback_expiring_the_source():
    """The retry must not re-read the source ORM instance.

    repository.create() rolls the session back on IntegrityError, which expires
    every loaded instance. Anything the retry still needs has to have been
    captured as a plain value before the loop — otherwise the second pass
    lazy-loads synchronously and raises MissingGreenlet instead of retrying.
    """
    source = _empty_children(_source_underwriting(version=0))
    repository = FakeRepository(
        source, conflict_versions={1}, poison_source_on_rollback=True
    )
    service = DuplicateUnderwritingService(repository)

    result = await service.duplicate(underwriting_id=42, current_user_id=99)

    assert result.version == 2
    # Both would be the poison values if the retry had re-read `source`.
    assert result.series_id == SERIES_ID
    assert result.copied_from_id == 42
    created = repository.created[0]["underwriting_data"]
    assert created["series_id"] == SERIES_ID
    assert created["copied_from_id"] == 42


@pytest.mark.asyncio
async def test_gives_up_after_exhausting_version_retries():
    source = _empty_children(_source_underwriting(version=0))
    repository = FakeRepository(source, conflict_versions={1, 2, 3})
    service = DuplicateUnderwritingService(repository)

    with pytest.raises(IntegrityError):
        await service.duplicate(underwriting_id=42, current_user_id=99)


@pytest.mark.asyncio
async def test_unrelated_integrity_errors_are_not_retried():
    source = _empty_children(_source_underwriting())
    repository = FakeRepository(source)

    async def failing_create(*args, **kwargs):
        raise IntegrityError("INSERT", {}, Exception("some other constraint"))

    repository.create = failing_create
    service = DuplicateUnderwritingService(repository)

    with pytest.raises(IntegrityError):
        await service.duplicate(underwriting_id=42, current_user_id=99)
    assert repository.version_reads == 1


@pytest.mark.asyncio
async def test_missing_source_raises_lookup_error():
    repository = FakeRepository(None)
    service = DuplicateUnderwritingService(repository)

    with pytest.raises(LookupError):
        await service.duplicate(underwriting_id=42, current_user_id=99)


@pytest.mark.asyncio
async def test_null_json_columns_are_copied_as_sql_null_not_json_null():
    """A NULL JSONB column must stay SQL NULL on the copy.

    SQLAlchemy's JSON/JSONB defaults to none_as_null=False, so a plain None
    would be written as the JSON scalar 'null'. Both read back as None in
    Python, but `WHERE col IS NULL` stops matching the copy — so the fork would
    differ from its source at the DB level.
    """
    source = _with_children(_source_underwriting())
    source.detail.forecasted_revenue = None
    source.detail.y1_coc_incl_tax_savings = None
    repository = FakeRepository(source)
    service = DuplicateUnderwritingService(repository)

    await service.duplicate(underwriting_id=42, current_user_id=99)
    detail_data = repository.created[0]["detail_data"]

    assert isinstance(detail_data["forecasted_revenue"], Null)
    assert isinstance(detail_data["y1_coc_incl_tax_savings"], Null)
    # non-null JSON and plain text columns are untouched
    assert detail_data["purchase_details"] == {"price": 750000}
    assert detail_data["analyst_notes"] == "detail notes"


@pytest.mark.asyncio
async def test_non_json_null_columns_stay_plain_none():
    """Only JSON columns need the null() treatment; scalars already map to NULL."""
    source = _empty_children(_source_underwriting(note=None, deal_complexity=None))
    repository = FakeRepository(source)
    service = DuplicateUnderwritingService(repository)

    await service.duplicate(underwriting_id=42, current_user_id=99)

    assert repository.created[0]["underwriting_data"]["deal_complexity"] is None
