from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.iron_bank.enums import DealStatus
from app.workflows.reconcile_underwriting_price_job import (
    ReconcileUnderwritingPriceJob,
)


class FakeListingsService:
    def __init__(self, listing):
        self.listing = listing

    async def get_by_zpid(self, zpid):
        return self.listing


class FakeRepository:
    def __init__(self, underwritings):
        self.underwritings = underwritings
        self.requested_zpid = None

    async def get_all_by_zpid(self, zpid):
        self.requested_zpid = zpid
        return self.underwritings


class FakeBuilder:
    normalize_purchase_price = staticmethod(
        lambda value: None if value is None else Decimal(str(value))
    )

    def __init__(self, payload=None, fail_for_ids=frozenset()):
        self.payload = payload or object()
        self.fail_for_ids = fail_for_ids
        self.received = []

    def build(self, *, underwriting, purchase_price):
        if underwriting.id in self.fail_for_ids:
            raise ValueError("existing taxes are required for price reconciliation")
        self.received.append(
            {"underwriting": underwriting, "purchase_price": purchase_price}
        )
        return self.payload


class FakeUpdateService:
    def __init__(self):
        self.received = []

    async def reconcile_purchase_price(self, underwriting_id, payload):
        self.received.append(
            {"underwriting_id": underwriting_id, "payload": payload}
        )


def _underwriting(
    id, *, version=0, purchase_price="485000", deal_status=DealStatus.ANALYST_STARTED
):
    return SimpleNamespace(
        id=id,
        version=version,
        purchase_price=None if purchase_price is None else Decimal(purchase_price),
        deal_status=deal_status.value if deal_status is not None else None,
    )


def make_job(*, underwritings, listing, builder=None, update_service=None):
    return ReconcileUnderwritingPriceJob(
        listings_service=FakeListingsService(listing),
        underwriting_repository=FakeRepository(underwritings),
        payload_builder=builder or FakeBuilder(),
        update_service=update_service or FakeUpdateService(),
    )


LISTING_AT_525K = SimpleNamespace(unformatted_price="525000", price=None)


@pytest.mark.asyncio
async def test_skips_when_no_underwriting_exists():
    result = await make_job(underwritings=[], listing=LISTING_AT_525K).run("1")

    assert result == {
        "zpid": "1",
        "status": "skipped_no_underwriting",
        "results": [],
    }


@pytest.mark.parametrize(
    "listing",
    [None, SimpleNamespace(unformatted_price=None, price=None)],
)
@pytest.mark.asyncio
async def test_skips_every_version_when_zillow_price_is_missing(listing):
    result = await make_job(
        underwritings=[_underwriting(10), _underwriting(11, version=1)],
        listing=listing,
    ).run("1")

    assert result["status"] == "skipped_no_purchase_price"
    assert result["results"] == [
        {"underwriting_id": 10, "version": 0, "status": "skipped_no_purchase_price"},
        {"underwriting_id": 11, "version": 1, "status": "skipped_no_purchase_price"},
    ]


@pytest.mark.asyncio
async def test_reconciles_every_version_of_the_series():
    """The whole point: a price change must reach all versions, not just one."""
    underwritings = [
        _underwriting(10, version=0),
        _underwriting(11, version=1),
        _underwriting(12, version=2),
    ]
    builder = FakeBuilder()
    update_service = FakeUpdateService()

    result = await make_job(
        underwritings=underwritings,
        listing=LISTING_AT_525K,
        builder=builder,
        update_service=update_service,
    ).run("1")

    assert result["status"] == "updated"
    assert [row["status"] for row in result["results"]] == ["updated"] * 3
    assert [row["underwriting_id"] for row in result["results"]] == [10, 11, 12]
    # every version was rebuilt at the new price and written
    assert [c["purchase_price"] for c in builder.received] == [Decimal("525000")] * 3
    assert [u["underwriting_id"] for u in update_service.received] == [10, 11, 12]


@pytest.mark.asyncio
async def test_skips_only_the_versions_already_at_that_price():
    update_service = FakeUpdateService()

    result = await make_job(
        underwritings=[
            _underwriting(10, version=0, purchase_price="525000"),
            _underwriting(11, version=1, purchase_price="485000"),
        ],
        listing=LISTING_AT_525K,
        update_service=update_service,
    ).run("1")

    assert [row["status"] for row in result["results"]] == [
        "skipped_same_price",
        "updated",
    ]
    # the unchanged version is not rewritten
    assert [u["underwriting_id"] for u in update_service.received] == [11]
    assert result["status"] == "updated"


@pytest.mark.parametrize(
    "terminal_status",
    [
        DealStatus.CLIENT_UNDER_CONTRACT,
        DealStatus.DELETE_DEAL,
        DealStatus.DELETE_ZILLOW,
        DealStatus.TRAINING_DEAL,
        DealStatus.PREVIOUSLY_UNDERWRITTEN_NO_STATUS,
    ],
)
@pytest.mark.asyncio
async def test_leaves_terminal_deals_alone(terminal_status):
    """A deal under contract has an agreed price Zillow no longer governs."""
    update_service = FakeUpdateService()

    result = await make_job(
        underwritings=[_underwriting(10, deal_status=terminal_status)],
        listing=LISTING_AT_525K,
        update_service=update_service,
    ).run("1")

    assert result["status"] == "skipped_terminal_status"
    assert result["results"][0]["status"] == "skipped_terminal_status"
    assert update_service.received == []


@pytest.mark.asyncio
async def test_terminal_versions_do_not_block_their_siblings():
    update_service = FakeUpdateService()

    result = await make_job(
        underwritings=[
            _underwriting(
                10, version=0, deal_status=DealStatus.CLIENT_UNDER_CONTRACT
            ),
            _underwriting(11, version=1),
        ],
        listing=LISTING_AT_525K,
        update_service=update_service,
    ).run("1")

    assert [row["status"] for row in result["results"]] == [
        "skipped_terminal_status",
        "updated",
    ]
    assert [u["underwriting_id"] for u in update_service.received] == [11]


@pytest.mark.asyncio
async def test_one_bad_version_does_not_stop_the_rest():
    """The builder rejects rows missing purchase details or taxes."""
    update_service = FakeUpdateService()
    builder = FakeBuilder(fail_for_ids={11})

    result = await make_job(
        underwritings=[
            _underwriting(10, version=0),
            _underwriting(11, version=1),
            _underwriting(12, version=2),
        ],
        listing=LISTING_AT_525K,
        builder=builder,
        update_service=update_service,
    ).run("1")

    assert [row["status"] for row in result["results"]] == [
        "updated",
        "failed",
        "updated",
    ]
    assert "taxes are required" in result["results"][1]["error"]
    # the versions either side of the failure still got written
    assert [u["underwriting_id"] for u in update_service.received] == [10, 12]


@pytest.mark.asyncio
async def test_a_partial_failure_is_never_reported_as_a_clean_run():
    result = await make_job(
        underwritings=[_underwriting(10, version=0), _underwriting(11, version=1)],
        listing=LISTING_AT_525K,
        builder=FakeBuilder(fail_for_ids={11}),
    ).run("1")

    # 'updated' would hide the failure from the batch rollup
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_reports_same_price_when_every_version_is_current():
    result = await make_job(
        underwritings=[
            _underwriting(10, version=0, purchase_price="525000"),
            _underwriting(11, version=1, purchase_price="525000"),
        ],
        listing=LISTING_AT_525K,
    ).run("1")

    assert result["status"] == "skipped_same_price"


class ExpiringUpdateService:
    """An update service whose failure expires every loaded ORM instance.

    That is what repository.update() does in production: it rolls the shared
    session back, and Session.rollback() expires *all* instances the session
    loaded — not just the failed row, and regardless of expire_on_commit. A
    detached SimpleNamespace can't reproduce the resulting MissingGreenlet, so
    the poisoned attributes stand in: any read of an underwriting after the
    first failure shows up in the assertions.
    """

    def __init__(self, underwritings, fail_for_ids):
        self.underwritings = underwritings
        self.fail_for_ids = fail_for_ids
        self.received = []

    async def reconcile_purchase_price(self, underwriting_id, payload):
        if underwriting_id in self.fail_for_ids:
            for underwriting in self.underwritings:
                underwriting.id = -1
                underwriting.version = -1
                underwriting.deal_status = "poisoned"
                underwriting.purchase_price = None
            raise RuntimeError("update failed")
        self.received.append(underwriting_id)


@pytest.mark.asyncio
async def test_a_failed_write_does_not_strand_the_remaining_versions():
    """The rollback behind a failed write must not break the rest of the loop."""
    underwritings = [
        _underwriting(10, version=0),
        _underwriting(11, version=1),
        _underwriting(12, version=2),
    ]
    update_service = ExpiringUpdateService(underwritings, fail_for_ids={10})

    result = await make_job(
        underwritings=underwritings,
        listing=LISTING_AT_525K,
        update_service=update_service,
    ).run("1")

    # versions 1 and 2 still ran, with their real ids — not the poisoned ones
    assert update_service.received == [11, 12]
    assert result["results"] == [
        {
            "underwriting_id": 10,
            "version": 0,
            "status": "failed",
            "error": "update failed",
        },
        {"underwriting_id": 11, "version": 1, "status": "updated"},
        {"underwriting_id": 12, "version": 2, "status": "updated"},
    ]
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_payloads_are_built_before_any_write():
    """All ORM reads must finish before the first write can expire anything."""
    underwritings = [_underwriting(10, version=0), _underwriting(11, version=1)]
    builder = FakeBuilder()
    update_service = ExpiringUpdateService(underwritings, fail_for_ids={10})

    await make_job(
        underwritings=underwritings,
        listing=LISTING_AT_525K,
        builder=builder,
        update_service=update_service,
    ).run("1")

    # both payloads were built up front, while the instances were still live
    assert len(builder.received) == 2
