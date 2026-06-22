# Purchase Price Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the daily underwriting batch to detect recent Zillow price changes and selectively recalculate existing underwritings without changing any non-price-dependent data.

**Architecture:** A dedicated builder will combine the new Zillow price with the underwriting's existing financial assumptions and child collections into an in-memory calculation payload. A reconciliation-specific `UpdateUnderwritingService` method will calculate new financial values but persist only an explicit allowlist. Single and batch workflow jobs will handle comparison, candidate selection, failure isolation, and CLI orchestration.

**Tech Stack:** Python 3.12, FastAPI service conventions, async SQLAlchemy, Pydantic, pytest/pytest-asyncio

---

## File Structure

- Create `app/iron_bank/services/purchase_price_reconciliation_payload_builder.py` for price normalization and building calculation-only payloads from existing underwriting assumptions.
- Modify `app/iron_bank/services/underwriting_payload_builder.py` to use the shared public price normalizer.
- Modify `app/iron_bank/services/update_underwriting_service.py` with a reconciliation-specific update method and strict persistence allowlist.
- Modify `app/iron_bank/repositories/underwriting_repository.py` so `get_by_zpid()` eagerly loads all child data needed by reconciliation.
- Modify `app/zillow/repositories/scheduled_listing_details_repository.py` and `app/zillow/services/scheduled_listing_details_service.py` to select recent price-change candidates.
- Create `app/workflows/reconcile_underwriting_price_job.py` for one `zpid`.
- Create `app/workflows/batch_reconcile_underwriting_prices_job.py` for candidate iteration and summary reporting.
- Modify `scripts/run_uw_auto_prepare.py` to run creation and reconciliation sequentially in batch mode.
- Add focused tests beside each affected layer.

### Task 1: Build the Reconciliation Calculation Payload

**Files:**
- Create: `app/iron_bank/services/purchase_price_reconciliation_payload_builder.py`
- Modify: `app/iron_bank/services/underwriting_payload_builder.py`
- Create: `tests/iron_bank/test_purchase_price_reconciliation_payload_builder.py`

- [ ] **Step 1: Write failing builder tests**

Create tests that demonstrate normalization and preservation of existing assumptions:

```python
from decimal import Decimal
from types import SimpleNamespace

from app.iron_bank.services.purchase_price_reconciliation_payload_builder import (
    PurchasePriceReconciliationPayloadBuilder,
)


def make_underwriting():
    return SimpleNamespace(
        detail=SimpleNamespace(
            purchase_details={
                "purchase_price": 485000,
                "down_payment_pct": 0.2,
                "interest_rate": 0.0675,
                "mortgage_years": 30,
                "closing_costs_pct": 0.03,
            },
            forecasted_revenue={
                "co_hosting_fee_pct": 0.1,
                "annual_re_appreciation_pct": 0.04,
                "scenarios": {
                    "low": {"forecasted_revenue": 72000, "annual_free_cash_flow": 1},
                    "mid": {"forecasted_revenue": 98000, "annual_free_cash_flow": 2},
                    "high": {"forecasted_revenue": 127000, "annual_free_cash_flow": 3},
                },
            },
        ),
        taxes=SimpleNamespace(
            land_assumptions_pct=Decimal("0.20"),
            sla_multiplier_pct=Decimal("0.36"),
            bonus_amount_pct=Decimal("1"),
            tax_rate_pct=Decimal("0.37"),
        ),
        optimization_items=[
            SimpleNamespace(
                category="Furniture",
                total_price=Decimal("20000"),
                metric=None,
                base_price=None,
                spec=None,
                tier=None,
            )
        ],
        operating_expenses=[
            SimpleNamespace(
                expense_name="Utilities",
                monthly_amount=Decimal("1000"),
            )
        ],
    )


def test_normalize_purchase_price_accepts_zillow_money_values():
    normalize = PurchasePriceReconciliationPayloadBuilder.normalize_purchase_price

    assert normalize("$525,000") == Decimal("525000")
    assert normalize(525000) == Decimal("525000")
    assert normalize(None) is None
    assert normalize("Contact for price") is None
    assert normalize(0) is None


def test_build_uses_new_price_and_existing_assumptions():
    payload = PurchasePriceReconciliationPayloadBuilder().build(
        underwriting=make_underwriting(),
        purchase_price=Decimal("525000"),
    )

    assert payload.details.purchase_details.purchase_price == Decimal("525000")
    assert payload.details.purchase_details.down_payment_pct == Decimal("0.2")
    assert payload.details.purchase_details.interest_rate == Decimal("0.0675")
    assert payload.details.forecasted_revenue.scenarios.mid.forecasted_revenue == Decimal("98000")
    assert payload.taxes.land_assumptions_pct == Decimal("0.20")
    assert payload.optimization_list[0].total_price == Decimal("20000")
    assert payload.operating_expenses[0].monthly_amount == Decimal("1000")
```

The existing `test_builds_save_payload_from_prepared_uw_data` already asserts
that `"$485,000"` becomes `Decimal("485000")`; retain that regression test.

- [ ] **Step 2: Run the builder tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/iron_bank/test_purchase_price_reconciliation_payload_builder.py tests/iron_bank/test_underwriting_payload_builder.py -v
```

Expected: collection fails because `PurchasePriceReconciliationPayloadBuilder` does not exist.

- [ ] **Step 3: Implement the reconciliation payload builder**

Create:

```python
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload


class PurchasePriceReconciliationPayloadBuilder:
    @staticmethod
    def normalize_purchase_price(value: Any) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value if value > 0 else None
        if isinstance(value, int | float):
            amount = Decimal(str(value))
            return amount if amount > 0 else None

        cleaned = re.sub(r"[^0-9.\-]", "", str(value))
        if not cleaned:
            return None
        try:
            amount = Decimal(cleaned)
        except InvalidOperation:
            return None
        return amount if amount > 0 else None

    def build(self, *, underwriting, purchase_price: Decimal) -> SaveUnderwritingPayload:
        if underwriting.detail is None or underwriting.detail.purchase_details is None:
            raise ValueError("existing purchase details are required for price reconciliation")
        if underwriting.detail.forecasted_revenue is None:
            raise ValueError("existing forecasted revenue is required for price reconciliation")
        if underwriting.taxes is None:
            raise ValueError("existing taxes are required for price reconciliation")

        purchase_details = underwriting.detail.purchase_details
        forecasted_revenue = underwriting.detail.forecasted_revenue
        payload = {
            "details": {
                "purchase_details": {
                    "purchase_price": purchase_price,
                    "down_payment_pct": purchase_details["down_payment_pct"],
                    "interest_rate": purchase_details["interest_rate"],
                    "mortgage_years": purchase_details["mortgage_years"],
                    "closing_costs_pct": purchase_details["closing_costs_pct"],
                },
                "forecasted_revenue": {
                    "co_hosting_fee_pct": forecasted_revenue["co_hosting_fee_pct"],
                    "annual_re_appreciation_pct": forecasted_revenue[
                        "annual_re_appreciation_pct"
                    ],
                    "scenarios": {
                        name: {
                            "forecasted_revenue": forecasted_revenue["scenarios"][name][
                                "forecasted_revenue"
                            ]
                        }
                        for name in ("low", "mid", "high")
                    },
                },
            },
            "taxes": {
                "land_assumptions_pct": underwriting.taxes.land_assumptions_pct,
                "sla_multiplier_pct": underwriting.taxes.sla_multiplier_pct,
                "bonus_amount_pct": underwriting.taxes.bonus_amount_pct,
                "tax_rate_pct": underwriting.taxes.tax_rate_pct,
            },
            "optimization_list": [
                {
                    "category": item.category,
                    "total_price": item.total_price,
                    "metric": item.metric,
                    "base_price": item.base_price,
                    "spec": item.spec,
                    "tier": item.tier,
                }
                for item in underwriting.optimization_items
            ],
            "operating_expenses": [
                {
                    "expense": expense.expense_name,
                    "monthly": expense.monthly_amount,
                }
                for expense in underwriting.operating_expenses
            ],
        }
        return SaveUnderwritingPayload.model_validate(payload)
```

Modify `UnderwritingPayloadBuilder._money_to_decimal()` to delegate to the new public normalizer, preserving its existing method for compatibility:

```python
from app.iron_bank.services.purchase_price_reconciliation_payload_builder import (
    PurchasePriceReconciliationPayloadBuilder,
)

def _money_to_decimal(self, value: Any) -> Decimal | None:
    return PurchasePriceReconciliationPayloadBuilder.normalize_purchase_price(value)
```

Remove the now-unused `InvalidOperation` and `re` imports from
`underwriting_payload_builder.py`.

- [ ] **Step 4: Run builder tests and verify they pass**

Run:

```bash
.venv/bin/pytest tests/iron_bank/test_purchase_price_reconciliation_payload_builder.py tests/iron_bank/test_underwriting_payload_builder.py -v
```

Expected: all builder tests pass.

- [ ] **Step 5: Commit the builder**

```bash
git add app/iron_bank/services/purchase_price_reconciliation_payload_builder.py app/iron_bank/services/underwriting_payload_builder.py tests/iron_bank/test_purchase_price_reconciliation_payload_builder.py
git commit -m "feat: build purchase price reconciliation payloads"
```

### Task 2: Add Selective Recalculation to the Update Service

**Files:**
- Modify: `app/iron_bank/services/update_underwriting_service.py`
- Modify: `tests/iron_bank/test_update_underwriting_service.py`

- [ ] **Step 1: Write the failing selective-update test**

Add a test using a complete calculation payload from Task 1:

```python
from decimal import Decimal

from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload


@pytest.mark.asyncio
async def test_reconcile_purchase_price_updates_only_price_dependent_data():
    repository = FakeUnderwritingRepository()
    service = UpdateUnderwritingService(repository)
    payload = SaveUnderwritingPayload.model_validate(
        {
            "details": {
                "purchase_details": {
                    "purchase_price": 525000,
                    "down_payment_pct": Decimal("0.20"),
                    "interest_rate": Decimal("0.06"),
                    "mortgage_years": 30,
                    "closing_costs_pct": Decimal("0.03"),
                },
                "forecasted_revenue": {
                    "co_hosting_fee_pct": Decimal("0.10"),
                    "annual_re_appreciation_pct": Decimal("0.04"),
                    "scenarios": {
                        "low": {"forecasted_revenue": 72000},
                        "mid": {"forecasted_revenue": 98000},
                        "high": {"forecasted_revenue": 127000},
                    },
                },
            },
            "taxes": {
                "land_assumptions_pct": Decimal("0.20"),
                "sla_multiplier_pct": Decimal("0.36"),
                "bonus_amount_pct": Decimal("1"),
                "tax_rate_pct": Decimal("0.37"),
            },
            "optimization_list": [{"category": "Furniture", "total_price": 20000}],
            "operating_expenses": [{"expense": "Utilities", "monthly": 1000}],
        }
    )

    result = await service.reconcile_purchase_price(42, payload)

    assert result.underwriting_id == 42
    kwargs = repository.update_kwargs
    assert set(kwargs["underwriting_data"]) == {
        "purchase_price",
        "total_oop",
        "prr",
        "budget_to_pp",
        "l_cash_on_cash",
        "m_cash_on_cash",
        "h_cash_on_cash",
    }
    assert set(kwargs["detail_data"]) == {
        "purchase_details",
        "forecasted_revenue",
        "y1_coc_incl_tax_savings",
    }
    assert kwargs["tax_data"] is not None
    assert kwargs["optimization_items"] is None
    assert kwargs["operating_expenses"] is None
    assert kwargs["comp_set"] is None
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/iron_bank/test_update_underwriting_service.py::test_reconcile_purchase_price_updates_only_price_dependent_data -v
```

Expected: fail because `reconcile_purchase_price()` does not exist.

- [ ] **Step 3: Implement the strict reconciliation method**

Add to `UpdateUnderwritingService`:

```python
from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload

_PRICE_RECONCILIATION_FIELDS = {
    "purchase_price",
    "total_oop",
    "prr",
    "budget_to_pp",
    "l_cash_on_cash",
    "m_cash_on_cash",
    "h_cash_on_cash",
}

async def reconcile_purchase_price(
    self,
    underwriting_id: int,
    payload: SaveUnderwritingPayload,
) -> UpdateUnderwritingResult:
    tax_data = self._build_tax_data(payload)
    detail_data = await self._build_detail_data(payload, tax_data)
    calculated_underwriting_data: dict = {}
    self._apply_calculated_underwriting_fields(
        calculated_underwriting_data,
        detail_data,
        payload.optimization_list,
    )
    underwriting_data = {
        key: value
        for key, value in calculated_underwriting_data.items()
        if key in self._PRICE_RECONCILIATION_FIELDS
    }

    underwriting = await self.repository.update(
        underwriting_id=underwriting_id,
        underwriting_data=underwriting_data,
        detail_data=jsonable_encoder(detail_data) if detail_data else None,
        tax_data=tax_data,
        optimization_items=None,
        operating_expenses=None,
        comp_set=None,
    )
    if underwriting is None:
        raise LookupError(f"Underwriting {underwriting_id} not found")
    return UpdateUnderwritingResult(underwriting_id=underwriting.id)
```

Keep the allowlist as a class constant named `_PRICE_RECONCILIATION_FIELDS`.

- [ ] **Step 4: Run update-service tests**

Run:

```bash
.venv/bin/pytest tests/iron_bank/test_update_underwriting_service.py -v
```

Expected: all update-service tests pass.

- [ ] **Step 5: Commit the selective update**

```bash
git add app/iron_bank/services/update_underwriting_service.py tests/iron_bank/test_update_underwriting_service.py
git commit -m "feat: selectively recalculate underwriting prices"
```

### Task 3: Load Reconciliation Candidates and Existing Child Data

**Files:**
- Modify: `app/iron_bank/repositories/underwriting_repository.py`
- Modify: `app/zillow/repositories/scheduled_listing_details_repository.py`
- Modify: `app/zillow/services/scheduled_listing_details_service.py`
- Create: `tests/zillow/test_scheduled_listing_details_service.py`

- [ ] **Step 1: Write a failing service delegation test**

```python
import pytest

from app.zillow.services.scheduled_listing_details_service import (
    ScheduledListingDetailsService,
)


class FakeDetailsRepository:
    def __init__(self):
        self.called_with = None

    async def get_price_changed_since(self, *, since_hours, limit):
        self.called_with = {"since_hours": since_hours, "limit": limit}
        return ["1", "2"]


@pytest.mark.asyncio
async def test_get_price_changed_zpids_since_delegates_window_and_limit():
    repository = FakeDetailsRepository()
    service = ScheduledListingDetailsService(repository)

    result = await service.get_price_changed_zpids_since(
        since_hours=24,
        limit=500,
    )

    assert result == ["1", "2"]
    assert repository.called_with == {"since_hours": 24, "limit": 500}
```

- [ ] **Step 2: Run the service test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/zillow/test_scheduled_listing_details_service.py -v
```

Expected: fail because `get_price_changed_zpids_since()` does not exist.

- [ ] **Step 3: Implement candidate selection and eager loading**

Add to `ScheduledListingDetailsRepository`:

```python
from datetime import datetime, timedelta, timezone

async def get_price_changed_since(
    self,
    *,
    since_hours: int,
    limit: int | None = None,
) -> list[str]:
    cutoff_date = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).date()
    query = (
        select(ScheduledListingDetail.zpid)
        .where(ScheduledListingDetail.price_change_date >= cutoff_date)
        .order_by(
            ScheduledListingDetail.price_change_date.desc(),
            ScheduledListingDetail.zpid,
        )
    )
    if limit is not None:
        query = query.limit(limit)
    result = await self.db.execute(query)
    return list(result.scalars().all())
```

Add the matching pass-through method to `ScheduledListingDetailsService`:

```python
async def get_price_changed_zpids_since(
    self,
    *,
    since_hours: int,
    limit: int | None = None,
) -> list[str]:
    return await self.repository.get_price_changed_since(
        since_hours=since_hours,
        limit=limit,
    )
```

Add the same `selectinload(...)` options used by `get_by_id()` to
`UnderwritingRepository.get_by_zpid()` so details, taxes, optimization items,
operating expenses, and comp set are available without async lazy loading.

- [ ] **Step 4: Run the Zillow service and underwriting workflow tests**

Run:

```bash
.venv/bin/pytest tests/zillow/test_scheduled_listing_details_service.py tests/workflows/test_prepare_and_save_underwriting_job.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit repository support**

```bash
git add app/iron_bank/repositories/underwriting_repository.py app/zillow/repositories/scheduled_listing_details_repository.py app/zillow/services/scheduled_listing_details_service.py tests/zillow/test_scheduled_listing_details_service.py
git commit -m "feat: select recent Zillow price changes"
```

### Task 4: Implement Single-Underwriting Price Reconciliation

**Files:**
- Create: `app/workflows/reconcile_underwriting_price_job.py`
- Create: `tests/workflows/test_reconcile_underwriting_price_job.py`

- [ ] **Step 1: Write failing single-job behavior tests**

Create the test module with these fakes and cases:

```python
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.workflows.reconcile_underwriting_price_job import (
    ReconcileUnderwritingPriceJob,
)


class FakeListingsService:
    def __init__(self, listing):
        self.listing = listing

    async def get_by_zpid(self, zpid):
        return self.listing


class FakeRepository:
    def __init__(self, underwriting):
        self.underwriting = underwriting

    async def get_by_zpid(self, zpid):
        return self.underwriting


class FakeBuilder:
    normalize_purchase_price = staticmethod(
        lambda value: None if value is None else Decimal(str(value))
    )

    def __init__(self, payload=None):
        self.payload = payload or object()
        self.received = None

    def build(self, *, underwriting, purchase_price):
        self.received = {
            "underwriting": underwriting,
            "purchase_price": purchase_price,
        }
        return self.payload


class FakeUpdateService:
    def __init__(self):
        self.received = None

    async def reconcile_purchase_price(self, underwriting_id, payload):
        self.received = {"underwriting_id": underwriting_id, "payload": payload}


def make_job(*, underwriting, listing, builder=None, update_service=None):
    return ReconcileUnderwritingPriceJob(
        listings_service=FakeListingsService(listing),
        underwriting_repository=FakeRepository(underwriting),
        payload_builder=builder or FakeBuilder(),
        update_service=update_service or FakeUpdateService(),
    )


@pytest.mark.asyncio
async def test_skips_when_underwriting_does_not_exist():
    result = await make_job(
        underwriting=None,
        listing=SimpleNamespace(unformatted_price="525000", price=None),
    ).run("1")

    assert result == {"zpid": "1", "status": "skipped_no_underwriting"}


@pytest.mark.parametrize(
    "listing",
    [None, SimpleNamespace(unformatted_price=None, price=None)],
)
@pytest.mark.asyncio
async def test_skips_when_zillow_purchase_price_is_missing(listing):
    result = await make_job(
        underwriting=SimpleNamespace(id=10, purchase_price=Decimal("485000")),
        listing=listing,
    ).run("1")

    assert result == {
        "zpid": "1",
        "status": "skipped_no_purchase_price",
        "underwriting_id": 10,
    }


@pytest.mark.asyncio
async def test_skips_when_purchase_price_is_unchanged():
    result = await make_job(
        underwriting=SimpleNamespace(id=10, purchase_price=Decimal("525000")),
        listing=SimpleNamespace(unformatted_price="525000", price=None),
    ).run("1")

    assert result == {
        "zpid": "1",
        "status": "skipped_same_price",
        "underwriting_id": 10,
    }


@pytest.mark.asyncio
async def test_reconciles_changed_purchase_price():
    underwriting = SimpleNamespace(id=10, purchase_price=Decimal("485000"))
    payload = object()
    builder = FakeBuilder(payload)
    update_service = FakeUpdateService()

    result = await make_job(
        underwriting=underwriting,
        listing=SimpleNamespace(unformatted_price="525000", price=None),
        builder=builder,
        update_service=update_service,
    ).run("1")

    assert result == {"zpid": "1", "status": "updated", "underwriting_id": 10}
    assert builder.received == {
        "underwriting": underwriting,
        "purchase_price": Decimal("525000"),
    }
    assert update_service.received == {
        "underwriting_id": 10,
        "payload": payload,
    }
```

- [ ] **Step 2: Run the job tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/workflows/test_reconcile_underwriting_price_job.py -v
```

Expected: collection fails because `ReconcileUnderwritingPriceJob` does not exist.

- [ ] **Step 3: Implement the single job and session wiring**

Create:

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.services.purchase_price_reconciliation_payload_builder import (
    PurchasePriceReconciliationPayloadBuilder,
)
from app.iron_bank.services.update_underwriting_service import UpdateUnderwritingService
from app.zillow.repositories.scheduled_listings_repository import ScheduledListingsRepository
from app.zillow.services.scheduled_listings_service import ScheduledListingsService


class ReconcileUnderwritingPriceJob:
    def __init__(
        self,
        *,
        listings_service,
        underwriting_repository,
        payload_builder,
        update_service,
    ):
        self.listings_service = listings_service
        self.underwriting_repository = underwriting_repository
        self.payload_builder = payload_builder
        self.update_service = update_service

    @classmethod
    def from_session(cls, db: AsyncSession) -> "ReconcileUnderwritingPriceJob":
        underwriting_repository = UnderwritingRepository(db)
        return cls(
            listings_service=ScheduledListingsService(ScheduledListingsRepository(db)),
            underwriting_repository=underwriting_repository,
            payload_builder=PurchasePriceReconciliationPayloadBuilder(),
            update_service=UpdateUnderwritingService(underwriting_repository),
        )

    async def run(self, zpid: str) -> dict:
        underwriting = await self.underwriting_repository.get_by_zpid(zpid)
        if underwriting is None:
            return {"zpid": zpid, "status": "skipped_no_underwriting"}

        listing = await self.listings_service.get_by_zpid(zpid)
        raw_price = (
            None
            if listing is None
            else listing.unformatted_price or listing.price
        )
        purchase_price = self.payload_builder.normalize_purchase_price(raw_price)
        if purchase_price is None:
            return {
                "zpid": zpid,
                "status": "skipped_no_purchase_price",
                "underwriting_id": underwriting.id,
            }
        if underwriting.purchase_price == purchase_price:
            return {
                "zpid": zpid,
                "status": "skipped_same_price",
                "underwriting_id": underwriting.id,
            }

        payload = self.payload_builder.build(
            underwriting=underwriting,
            purchase_price=purchase_price,
        )
        await self.update_service.reconcile_purchase_price(underwriting.id, payload)
        return {
            "zpid": zpid,
            "status": "updated",
            "underwriting_id": underwriting.id,
        }
```

- [ ] **Step 4: Run the single-job tests**

Run:

```bash
.venv/bin/pytest tests/workflows/test_reconcile_underwriting_price_job.py -v
```

Expected: all single-job tests pass.

- [ ] **Step 5: Commit the single job**

```bash
git add app/workflows/reconcile_underwriting_price_job.py tests/workflows/test_reconcile_underwriting_price_job.py
git commit -m "feat: reconcile one underwriting purchase price"
```

### Task 5: Implement Batch Reconciliation

**Files:**
- Create: `app/workflows/batch_reconcile_underwriting_prices_job.py`
- Create: `tests/workflows/test_batch_reconcile_underwriting_prices_job.py`

- [ ] **Step 1: Write the failing batch summary test**

Create fakes matching the existing batch-job test style. Use four `zpid`s with
results `updated`, `skipped_same_price`, `skipped_no_underwriting`, and an
exception. Assert the candidate service receives `since_hours=24, limit=500`
and the summary equals:

```python
{
    "found": 4,
    "processed": 4,
    "updated": 1,
    "skipped_same_price": 1,
    "skipped_no_underwriting": 1,
    "skipped_no_purchase_price": 0,
    "failed": 1,
    "results": [
        {"zpid": "1", "status": "updated", "underwriting_id": 10},
        {"zpid": "2", "status": "skipped_same_price", "underwriting_id": 20},
        {"zpid": "3", "status": "skipped_no_underwriting"},
        {"zpid": "4", "status": "failed", "error": "boom"},
    ],
}
```

- [ ] **Step 2: Run the batch test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/workflows/test_batch_reconcile_underwriting_prices_job.py -v
```

Expected: collection fails because `BatchReconcileUnderwritingPricesJob` does not exist.

- [ ] **Step 3: Implement the batch job**

Create:

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.workflows.reconcile_underwriting_price_job import (
    ReconcileUnderwritingPriceJob,
)
from app.zillow.repositories.scheduled_listing_details_repository import (
    ScheduledListingDetailsRepository,
)
from app.zillow.services.scheduled_listing_details_service import (
    ScheduledListingDetailsService,
)


class BatchReconcileUnderwritingPricesJob:
    def __init__(self, *, listing_details_service, reconcile_job):
        self.listing_details_service = listing_details_service
        self.reconcile_job = reconcile_job

    @classmethod
    def from_session(cls, db: AsyncSession) -> "BatchReconcileUnderwritingPricesJob":
        return cls(
            listing_details_service=ScheduledListingDetailsService(
                ScheduledListingDetailsRepository(db)
            ),
            reconcile_job=ReconcileUnderwritingPriceJob.from_session(db),
        )

    async def run(self, *, since_hours: int, limit: int | None = None) -> dict:
        zpids = await self.listing_details_service.get_price_changed_zpids_since(
            since_hours=since_hours,
            limit=limit,
        )
        counts = {
            "updated": 0,
            "skipped_same_price": 0,
            "skipped_no_underwriting": 0,
            "skipped_no_purchase_price": 0,
            "failed": 0,
        }
        results = []
        for zpid in zpids:
            try:
                result = await self.reconcile_job.run(zpid)
            except Exception as exc:
                counts["failed"] += 1
                results.append({"zpid": zpid, "status": "failed", "error": str(exc)})
                continue
            counts[result["status"]] += 1
            results.append(result)
        return {
            "found": len(zpids),
            "processed": len(results),
            **counts,
            "results": results,
        }
```

- [ ] **Step 4: Run both reconciliation workflow test modules**

Run:

```bash
.venv/bin/pytest tests/workflows/test_reconcile_underwriting_price_job.py tests/workflows/test_batch_reconcile_underwriting_prices_job.py -v
```

Expected: all reconciliation workflow tests pass.

- [ ] **Step 5: Commit the batch job**

```bash
git add app/workflows/batch_reconcile_underwriting_prices_job.py tests/workflows/test_batch_reconcile_underwriting_prices_job.py
git commit -m "feat: batch recent price reconciliations"
```

### Task 6: Wire Reconciliation into the Daily CLI

**Files:**
- Modify: `scripts/run_uw_auto_prepare.py`
- Modify: `tests/scripts/test_run_uw_auto_prepare.py`

- [ ] **Step 1: Write the failing combined-batch test**

Replace the batch fake with separate creation and reconciliation fakes, then
assert:

```python
summary = await run_uw_auto_prepare.run_batch(
    since_hours=24,
    limit=500,
    session_factory=FakeSessionFactory,
    creation_job_cls=FakeCreationJob,
    reconciliation_job_cls=FakeReconciliationJob,
)

assert summary == {
    "creation": {"saved": 2, "failed": 0},
    "price_reconciliation": {"updated": 1, "failed": 0},
}
assert FakeCreationJob.called_with == {"since_hours": 24, "limit": 500}
assert FakeReconciliationJob.called_with == {"since_hours": 24, "limit": 500}
```

- [ ] **Step 2: Run the script tests and verify the new test fails**

Run:

```bash
.venv/bin/pytest tests/scripts/test_run_uw_auto_prepare.py -v
```

Expected: fail because `run_batch()` does not accept the two job classes or
return the combined summary.

- [ ] **Step 3: Implement sequential batch orchestration**

Import `BatchReconcileUnderwritingPricesJob` and change `run_batch()` to:

```python
async def run_batch(
    *,
    since_hours: int,
    limit: int | None,
    session_factory=AsyncSessionLocal,
    creation_job_cls=BatchPrepareAndSaveUnderwritingsJob,
    reconciliation_job_cls=BatchReconcileUnderwritingPricesJob,
) -> dict[str, Any]:
    async with session_factory() as session:
        creation = await creation_job_cls.from_session(session).run(
            since_hours=since_hours,
            limit=limit,
        )
        price_reconciliation = await reconciliation_job_cls.from_session(session).run(
            since_hours=since_hours,
            limit=limit,
        )
        return {
            "creation": creation,
            "price_reconciliation": price_reconciliation,
        }
```

Do not change `run_single()`.

- [ ] **Step 4: Run script and workflow tests**

Run:

```bash
.venv/bin/pytest tests/scripts/test_run_uw_auto_prepare.py tests/workflows -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit CLI integration**

```bash
git add scripts/run_uw_auto_prepare.py tests/scripts/test_run_uw_auto_prepare.py
git commit -m "feat: run price reconciliation in daily batch"
```

### Task 7: Verify the Complete Feature

**Files:**
- Verify all files changed in Tasks 1-6.

- [ ] **Step 1: Run focused reconciliation tests**

```bash
.venv/bin/pytest tests/iron_bank/test_purchase_price_reconciliation_payload_builder.py tests/iron_bank/test_update_underwriting_service.py tests/zillow/test_scheduled_listing_details_service.py tests/workflows/test_reconcile_underwriting_price_job.py tests/workflows/test_batch_reconcile_underwriting_prices_job.py tests/scripts/test_run_uw_auto_prepare.py -v
```

Expected: all focused tests pass.

- [ ] **Step 2: Run lint checks**

```bash
.venv/bin/ruff check app/iron_bank/services/purchase_price_reconciliation_payload_builder.py app/iron_bank/services/underwriting_payload_builder.py app/iron_bank/services/update_underwriting_service.py app/iron_bank/repositories/underwriting_repository.py app/zillow/repositories/scheduled_listing_details_repository.py app/zillow/services/scheduled_listing_details_service.py app/workflows/reconcile_underwriting_price_job.py app/workflows/batch_reconcile_underwriting_prices_job.py scripts/run_uw_auto_prepare.py tests/iron_bank/test_purchase_price_reconciliation_payload_builder.py tests/iron_bank/test_update_underwriting_service.py tests/zillow/test_scheduled_listing_details_service.py tests/workflows/test_reconcile_underwriting_price_job.py tests/workflows/test_batch_reconcile_underwriting_prices_job.py tests/scripts/test_run_uw_auto_prepare.py
```

Expected: `All checks passed!`

- [ ] **Step 3: Run the full test suite and compare with baseline**

```bash
.venv/bin/pytest -q
```

Expected: no new failures beyond the five already-recorded baseline failures in
deal-status labels and PRR expectations. All new reconciliation tests must pass.

- [ ] **Step 4: Review workspace scope**

```bash
git diff --check
git status --short
git log --oneline -7
```

Expected: no whitespace errors; unrelated user changes remain unstaged and
untouched; the reconciliation work is represented by the scoped commits above.
