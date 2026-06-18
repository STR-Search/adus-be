# Iron Bank Enums Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deal-status workflow support first, then add a reusable `iron_bank` reference-data enum system for FE option discovery and dynamic tag/dropdown fields.

**Architecture:** Phase 1 treats `deal_status` as workflow state: code-owned `StrEnum`, `VARCHAR` storage, DB `CHECK` constraint, FE labels/options from code, and a service that owns valid transitions plus role-based transition authorization. Phase 2 adds DB-backed enum/reference tables for tag-like fields only, with labels, ordering, metadata, active/inactive state, service-level validation, and one FE endpoint for underwriting edit options.

**Tech Stack:** FastAPI, Pydantic v2, async SQLAlchemy, Alembic, PostgreSQL schemas `iron_bank` and `markets`, pytest.

---

## File Structure

### Phase 1: Deal Status

- Create: `app/iron_bank/enums.py`
  - Owns workflow enum constants such as `DealStatus.ANALYST_STARTED`.
- Create: `app/iron_bank/schemas/deal_status.py`
  - Response models for deal-status options and transitions.
- Create: `app/iron_bank/services/deal_status_service.py`
  - Owns label mapping, sort order, valid transitions, and actor-role authorization.
- Create: `app/iron_bank/controllers/deal_status_controller.py`
  - Exposes deal-status options and allowed transitions to FE.
- Modify: `app/iron_bank/models/underwriting.py`
  - Keeps `deal_status` as `String(50)` and adds/checks naming alignment.
- Modify: `app/iron_bank/schemas/underwriting.py`
  - Types `deal_status` as `DealStatus | None`.
- Modify: `app/iron_bank/schemas/update_underwriting.py`
  - Types `deal_status` as `DealStatus | None`.
- Modify: `app/iron_bank/router.py`
  - Adds `GET /iron-bank/deal-statuses` and `GET /iron-bank/deal-statuses/transitions`.
- Create: `migrations/versions/<revision>_add_deal_status_check.py`
  - Adds a `CHECK` constraint to `iron_bank.underwritings.deal_status`.
- Test: `tests/iron_bank/test_deal_status_service.py`
  - Verifies labels, stable keys, transition rules, and role authorization.
- Test: `tests/iron_bank/test_deal_status_controller.py`
  - Verifies FE response shape for options and transitions.
- Test: `tests/iron_bank/test_update_underwriting_schema.py`
  - Verifies invalid deal statuses are rejected by Pydantic.
- Test: `tests/iron_bank/test_save_underwriting_schema.py`
  - Verifies valid deal statuses are accepted.

### Phase 2: Iron Bank Enum System

- Create: `app/iron_bank/models/reference_data.py`
  - Defines `EnumSet` and `EnumOption` models in schema `iron_bank`.
- Modify: `app/iron_bank/models/__init__.py`
  - Imports reference-data models for Alembic discovery.
- Create: `app/iron_bank/schemas/reference_data.py`
  - Response models for enum sets and options.
- Create: `app/iron_bank/repositories/reference_data_repository.py`
  - Fetches active/all enum options from DB.
- Create: `app/iron_bank/services/reference_data_service.py`
  - Groups options by set, validates active keys, and caches read responses.
- Create: `app/iron_bank/controllers/reference_data_controller.py`
  - Exposes underwriting reference data.
- Modify: `app/iron_bank/router.py`
  - Adds `GET /iron-bank/reference-data/underwritings`.
- Modify: `app/iron_bank/schemas/underwriting.py`
  - Converts tag-like Python enum fields to `str | None`.
- Modify: `app/iron_bank/schemas/update_underwriting.py`
  - Converts tag-like Python enum fields to `str | None`.
- Modify: `app/iron_bank/services/save_underwriting_service.py`
  - Validates tag-like values against active reference options.
- Modify: `app/iron_bank/services/update_underwriting_service.py`
  - Reuses save validation for update payloads.
- Create: `migrations/versions/<revision>_add_iron_bank_enum_reference_data.py`
  - Creates and seeds `iron_bank.enum_sets` and `iron_bank.enum_options`.
- Test: `tests/iron_bank/test_reference_data_repository.py`
  - Verifies DB option reads.
- Test: `tests/iron_bank/test_reference_data_service.py`
  - Verifies grouping, validation, and cache behavior.
- Test: `tests/iron_bank/test_reference_data_controller.py`
  - Verifies FE endpoint response.
- Test: `tests/iron_bank/test_save_underwriting_service.py`
  - Verifies invalid tag values fail before persistence.
- Test: `tests/iron_bank/test_update_underwriting_service.py`
  - Verifies invalid tag values fail on update.

---

## Phase 1: Deal Status Hardening

### Task 1: Define DealStatus Enum

**Files:**
- Create: `app/iron_bank/enums.py`
- Test: `tests/iron_bank/test_save_underwriting_schema.py`
- Test: `tests/iron_bank/test_update_underwriting_schema.py`

- [ ] **Step 1: Use current deal statuses**

Use these stable keys and display labels:

```text
template_generated       -> Template_generated
analyst_started          -> Analyst Started
analyst_completed        -> Analyst Completed
delete_zillow            -> Delete - Zillow
delete_deal              -> Delete - Deal
maybe                    -> Maybe
re_forecast_revenue      -> Re-Forecast Revenue
awaiting_realtor_details -> Awaiting Realtor Details
present_to_clients       -> Present To Clients
client_under_contract    -> Client Under Contract
training_deal            -> Training Deal
```

Store the stable key in `underwritings.deal_status`. Return the display label to FE from `/iron-bank/deal-statuses`. Deal status remains code-owned workflow state; do not seed it into the Phase 2 DB reference-data tables.

- [ ] **Step 2: Add failing schema tests**

Add save/update tests that expect valid values to parse and invalid values to fail:

```python
import pytest
from pydantic import ValidationError

from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload
from app.iron_bank.schemas.update_underwriting import UpdateUnderwritingPayload


def test_save_underwriting_accepts_valid_deal_status():
    payload = SaveUnderwritingPayload.model_validate({"deal_status": "analyst_started"})
    assert payload.deal_status == DealStatus.ANALYST_STARTED


def test_save_underwriting_rejects_invalid_deal_status():
    with pytest.raises(ValidationError):
        SaveUnderwritingPayload.model_validate({"deal_status": "not_real"})


def test_update_underwriting_accepts_valid_deal_status():
    payload = UpdateUnderwritingPayload.model_validate({"deal_status": "client_under_contract"})
    assert payload.deal_status == DealStatus.CLIENT_UNDER_CONTRACT


def test_update_underwriting_rejects_invalid_deal_status():
    with pytest.raises(ValidationError):
        UpdateUnderwritingPayload.model_validate({"deal_status": "not_real"})
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
pytest tests/iron_bank/test_save_underwriting_schema.py tests/iron_bank/test_update_underwriting_schema.py -v
```

Expected: failures because `DealStatus` does not exist or `deal_status` is still typed as `str`.

- [ ] **Step 4: Implement `DealStatus`**

Create `app/iron_bank/enums.py`:

```python
from enum import StrEnum


class DealStatus(StrEnum):
    TEMPLATE_GENERATED = "template_generated"
    ANALYST_STARTED = "analyst_started"
    ANALYST_COMPLETED = "analyst_completed"
    DELETE_ZILLOW = "delete_zillow"
    DELETE_DEAL = "delete_deal"
    MAYBE = "maybe"
    RE_FORECAST_REVENUE = "re_forecast_revenue"
    AWAITING_REALTOR_DETAILS = "awaiting_realtor_details"
    PRESENT_TO_CLIENTS = "present_to_clients"
    CLIENT_UNDER_CONTRACT = "client_under_contract"
    TRAINING_DEAL = "training_deal"
```

- [ ] **Step 5: Type schemas with `DealStatus`**

Update `deal_status` in:

```python
from app.iron_bank.enums import DealStatus

deal_status: DealStatus | None = None
```

Apply this to `app/iron_bank/schemas/underwriting.py` and `app/iron_bank/schemas/update_underwriting.py`.

- [ ] **Step 6: Run schema tests**

Run:

```bash
pytest tests/iron_bank/test_save_underwriting_schema.py tests/iron_bank/test_update_underwriting_schema.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Phase 1 enum typing**

```bash
git add app/iron_bank/enums.py app/iron_bank/schemas/underwriting.py app/iron_bank/schemas/update_underwriting.py tests/iron_bank/test_save_underwriting_schema.py tests/iron_bank/test_update_underwriting_schema.py
git commit -m "feat: add deal status enum"
```

### Task 2: Add Deal Status Workflow Service

**Files:**
- Create: `app/iron_bank/schemas/deal_status.py`
- Create: `app/iron_bank/services/deal_status_service.py`
- Test: `tests/iron_bank/test_deal_status_service.py`

- [ ] **Step 1: Add failing service tests**

Create `tests/iron_bank/test_deal_status_service.py`:

```python
import pytest

from app.iron_bank.enums import DealStatus
from app.iron_bank.services.deal_status_service import (
    DealStatusService,
    DealStatusTransitionError,
)


def test_list_status_options_returns_fe_labels_and_stable_keys():
    result = DealStatusService().list_status_options()

    assert result.statuses[0].model_dump() == {
        "key": "template_generated",
        "label": "Template_generated",
        "sort_order": 1,
    }


def test_allowed_transitions_filters_by_actor_role():
    result = DealStatusService().get_allowed_transitions(
        current_status=DealStatus.ANALYST_STARTED,
        actor_role="analyst",
    )

    assert [option.key for option in result.allowed_transitions] == [
        "analyst_completed",
        "maybe",
        "re_forecast_revenue",
    ]


def test_validate_transition_rejects_role_without_permission():
    service = DealStatusService()

    with pytest.raises(DealStatusTransitionError):
        service.validate_transition(
            current_status=DealStatus.ANALYST_STARTED,
            next_status=DealStatus.PRESENT_TO_CLIENTS,
            actor_role="analyst",
        )
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
pytest tests/iron_bank/test_deal_status_service.py -v
```

Expected: FAIL because service/schema do not exist.

- [ ] **Step 3: Add schemas**

Create `app/iron_bank/schemas/deal_status.py`:

```python
from pydantic import BaseModel


class DealStatusOption(BaseModel):
    key: str
    label: str
    sort_order: int


class DealStatusOptionsResult(BaseModel):
    statuses: list[DealStatusOption]


class DealStatusTransitionsResult(BaseModel):
    current_status: str
    actor_role: str
    allowed_transitions: list[DealStatusOption]
```

- [ ] **Step 4: Add service**

Create `app/iron_bank/services/deal_status_service.py`:

```python
from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.deal_status import (
    DealStatusOption,
    DealStatusOptionsResult,
    DealStatusTransitionsResult,
)


class DealStatusTransitionError(ValueError):
    pass


STATUS_OPTIONS: tuple[tuple[DealStatus, str, int], ...] = (
    (DealStatus.TEMPLATE_GENERATED, "Template_generated", 1),
    (DealStatus.ANALYST_STARTED, "Analyst Started", 2),
    (DealStatus.ANALYST_COMPLETED, "Analyst Completed", 3),
    (DealStatus.DELETE_ZILLOW, "Delete - Zillow", 4),
    (DealStatus.DELETE_DEAL, "Delete - Deal", 5),
    (DealStatus.MAYBE, "Maybe", 6),
    (DealStatus.RE_FORECAST_REVENUE, "Re-Forecast Revenue", 7),
    (DealStatus.AWAITING_REALTOR_DETAILS, "Awaiting Realtor Details", 8),
    (DealStatus.PRESENT_TO_CLIENTS, "Present To Clients", 9),
    (DealStatus.CLIENT_UNDER_CONTRACT, "Client Under Contract", 10),
    (DealStatus.TRAINING_DEAL, "Training Deal", 11),
)

DEAL_STATUS_TRANSITIONS: dict[DealStatus, set[DealStatus]] = {
    DealStatus.TEMPLATE_GENERATED: {
        DealStatus.ANALYST_STARTED,
        DealStatus.TRAINING_DEAL,
        DealStatus.DELETE_ZILLOW,
        DealStatus.DELETE_DEAL,
    },
    DealStatus.ANALYST_STARTED: {
        DealStatus.ANALYST_COMPLETED,
        DealStatus.MAYBE,
        DealStatus.RE_FORECAST_REVENUE,
        DealStatus.DELETE_ZILLOW,
        DealStatus.DELETE_DEAL,
    },
    DealStatus.ANALYST_COMPLETED: {
        DealStatus.AWAITING_REALTOR_DETAILS,
        DealStatus.PRESENT_TO_CLIENTS,
        DealStatus.MAYBE,
        DealStatus.RE_FORECAST_REVENUE,
        DealStatus.DELETE_DEAL,
    },
    DealStatus.AWAITING_REALTOR_DETAILS: {
        DealStatus.PRESENT_TO_CLIENTS,
        DealStatus.RE_FORECAST_REVENUE,
        DealStatus.MAYBE,
        DealStatus.DELETE_DEAL,
    },
    DealStatus.PRESENT_TO_CLIENTS: {
        DealStatus.CLIENT_UNDER_CONTRACT,
        DealStatus.MAYBE,
        DealStatus.RE_FORECAST_REVENUE,
        DealStatus.DELETE_DEAL,
    },
    DealStatus.MAYBE: {
        DealStatus.ANALYST_STARTED,
        DealStatus.RE_FORECAST_REVENUE,
        DealStatus.DELETE_DEAL,
    },
    DealStatus.RE_FORECAST_REVENUE: {
        DealStatus.ANALYST_STARTED,
        DealStatus.ANALYST_COMPLETED,
        DealStatus.DELETE_DEAL,
    },
    DealStatus.CLIENT_UNDER_CONTRACT: set(),
    DealStatus.TRAINING_DEAL: set(),
    DealStatus.DELETE_ZILLOW: set(),
    DealStatus.DELETE_DEAL: set(),
}

ROLE_ALLOWED_TARGETS: dict[str, set[DealStatus]] = {
    "analyst": {
        DealStatus.ANALYST_STARTED,
        DealStatus.ANALYST_COMPLETED,
        DealStatus.MAYBE,
        DealStatus.RE_FORECAST_REVENUE,
    },
    "approver": {
        DealStatus.AWAITING_REALTOR_DETAILS,
        DealStatus.PRESENT_TO_CLIENTS,
        DealStatus.CLIENT_UNDER_CONTRACT,
        DealStatus.MAYBE,
        DealStatus.RE_FORECAST_REVENUE,
    },
    "admin": set(DealStatus),
}


class DealStatusService:
    def list_status_options(self) -> DealStatusOptionsResult:
        return DealStatusOptionsResult(
            statuses=[self._to_option(status) for status, _, _ in STATUS_OPTIONS]
        )

    def get_allowed_transitions(
        self,
        *,
        current_status: DealStatus,
        actor_role: str,
    ) -> DealStatusTransitionsResult:
        valid_targets = DEAL_STATUS_TRANSITIONS[current_status]
        role_targets = ROLE_ALLOWED_TARGETS.get(actor_role, set())
        allowed = valid_targets & role_targets

        return DealStatusTransitionsResult(
            current_status=current_status.value,
            actor_role=actor_role,
            allowed_transitions=[
                self._to_option(status)
                for status, _, _ in STATUS_OPTIONS
                if status in allowed
            ],
        )

    def validate_transition(
        self,
        *,
        current_status: DealStatus,
        next_status: DealStatus,
        actor_role: str,
    ) -> None:
        allowed = {
            option.key
            for option in self.get_allowed_transitions(
                current_status=current_status,
                actor_role=actor_role,
            ).allowed_transitions
        }
        if next_status.value not in allowed:
            raise DealStatusTransitionError(
                f"{actor_role} cannot transition deal_status from "
                f"{current_status.value} to {next_status.value}"
            )

    def _to_option(self, status: DealStatus) -> DealStatusOption:
        for candidate, label, sort_order in STATUS_OPTIONS:
            if candidate == status:
                return DealStatusOption(
                    key=status.value,
                    label=label,
                    sort_order=sort_order,
                )
        raise ValueError(f"Unknown deal status: {status}")
```

- [ ] **Step 5: Run service tests**

Run:

```bash
pytest tests/iron_bank/test_deal_status_service.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit service**

```bash
git add app/iron_bank/schemas/deal_status.py app/iron_bank/services/deal_status_service.py tests/iron_bank/test_deal_status_service.py
git commit -m "feat: add deal status workflow service"
```

### Task 3: Add Deal Status FE Endpoints

**Files:**
- Create: `app/iron_bank/controllers/deal_status_controller.py`
- Modify: `app/iron_bank/router.py`
- Test: `tests/iron_bank/test_deal_status_controller.py`

- [ ] **Step 1: Add failing controller tests**

Create `tests/iron_bank/test_deal_status_controller.py`:

```python
from app.iron_bank.controllers.deal_status_controller import DealStatusController
from app.iron_bank.enums import DealStatus
from app.iron_bank.services.deal_status_service import DealStatusService


def test_get_deal_statuses_returns_fe_options():
    result = DealStatusController(DealStatusService()).get_deal_statuses()

    assert result.statuses[0].model_dump() == {
        "key": "template_generated",
        "label": "Template_generated",
        "sort_order": 1,
    }


def test_get_allowed_transitions_returns_role_filtered_targets():
    result = DealStatusController(DealStatusService()).get_allowed_transitions(
        current_status=DealStatus.ANALYST_STARTED,
        actor_role="analyst",
    )

    assert [option.key for option in result.allowed_transitions] == [
        "analyst_completed",
        "maybe",
        "re_forecast_revenue",
    ]
```

- [ ] **Step 2: Run controller tests and verify failure**

Run:

```bash
pytest tests/iron_bank/test_deal_status_controller.py -v
```

Expected: FAIL because controller does not exist.

- [ ] **Step 3: Add controller**

Create `app/iron_bank/controllers/deal_status_controller.py`:

```python
from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.deal_status import (
    DealStatusOptionsResult,
    DealStatusTransitionsResult,
)
from app.iron_bank.services.deal_status_service import DealStatusService


class DealStatusController:
    def __init__(self, service: DealStatusService):
        self.service = service

    def get_deal_statuses(self) -> DealStatusOptionsResult:
        return self.service.list_status_options()

    def get_allowed_transitions(
        self,
        *,
        current_status: DealStatus,
        actor_role: str,
    ) -> DealStatusTransitionsResult:
        return self.service.get_allowed_transitions(
            current_status=current_status,
            actor_role=actor_role,
        )
```

- [ ] **Step 4: Wire routes**

Modify `app/iron_bank/router.py`:

```python
from app.iron_bank.controllers.deal_status_controller import DealStatusController
from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.deal_status import (
    DealStatusOptionsResult,
    DealStatusTransitionsResult,
)
from app.iron_bank.services.deal_status_service import DealStatusService


def get_deal_status_controller() -> DealStatusController:
    return DealStatusController(DealStatusService())


@router.get(
    "/deal-statuses",
    response_model=DealStatusOptionsResult,
    tags=["iron_bank"],
)
async def get_deal_statuses(
    controller: DealStatusController = Depends(get_deal_status_controller),
):
    return controller.get_deal_statuses()


@router.get(
    "/deal-statuses/transitions",
    response_model=DealStatusTransitionsResult,
    tags=["iron_bank"],
)
async def get_deal_status_transitions(
    current_status: DealStatus,
    actor_role: str,
    controller: DealStatusController = Depends(get_deal_status_controller),
):
    return controller.get_allowed_transitions(
        current_status=current_status,
        actor_role=actor_role,
    )
```

Until real auth dependencies exist, `actor_role` is accepted as a query parameter for transition preview. Once auth is wired, replace that query parameter with a trusted role from the authenticated user/session.

- [ ] **Step 5: Run controller tests**

Run:

```bash
pytest tests/iron_bank/test_deal_status_controller.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit endpoints**

```bash
git add app/iron_bank/controllers/deal_status_controller.py app/iron_bank/router.py tests/iron_bank/test_deal_status_controller.py
git commit -m "feat: expose deal status workflow endpoints"
```

### Task 4: Add DB CHECK Constraint for Deal Status

**Files:**
- Modify: `app/iron_bank/models/underwriting.py`
- Create: `migrations/versions/<revision>_add_deal_status_check.py`

- [ ] **Step 1: Update model with named check constraint**

Add `CheckConstraint` import and update `Underwriting.__table_args__`:

```python
from sqlalchemy import CheckConstraint

__table_args__ = (
    CheckConstraint(
        "deal_status IS NULL OR deal_status IN ('template_generated', 'analyst_started', 'analyst_completed', 'delete_zillow', 'delete_deal', 'maybe', 're_forecast_revenue', 'awaiting_realtor_details', 'present_to_clients', 'client_under_contract', 'training_deal')",
        name="ck_underwritings_deal_status",
    ),
    {"schema": "iron_bank"},
)
```

- [ ] **Step 2: Generate or write migration**

Create an Alembic migration that adds the same constraint:

```python
from alembic import op


def upgrade() -> None:
    op.create_check_constraint(
        "ck_underwritings_deal_status",
        "underwritings",
        "deal_status IS NULL OR deal_status IN ('template_generated', 'analyst_started', 'analyst_completed', 'delete_zillow', 'delete_deal', 'maybe', 're_forecast_revenue', 'awaiting_realtor_details', 'present_to_clients', 'client_under_contract', 'training_deal')",
        schema="iron_bank",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_underwritings_deal_status",
        "underwritings",
        schema="iron_bank",
        type_="check",
    )
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
pytest tests/iron_bank/test_deal_status_service.py tests/iron_bank/test_deal_status_controller.py tests/iron_bank/test_save_underwriting_schema.py tests/iron_bank/test_update_underwriting_schema.py -v
```

Expected: PASS.

- [ ] **Step 4: Inspect migration heads**

Run:

```bash
alembic heads
```

Expected: both migration branches remain valid; no accidental `public` schema changes.

- [ ] **Step 5: Commit DB constraint**

```bash
git add app/iron_bank/models/underwriting.py migrations/versions
git commit -m "feat: constrain underwriting deal status"
```

### Phase 1 Verification

- [ ] Run:

```bash
pytest tests/iron_bank -v
```

- [ ] Run:

```bash
alembic upgrade heads
```

- [ ] Confirm:

```text
GET /iron-bank/deal-statuses returns all deal-status keys, labels, and sort order.
GET /iron-bank/deal-statuses/transitions returns valid target statuses filtered by actor role.
Invalid deal_status values fail API validation.
The database rejects invalid deal_status values.
Transition enforcement methods exist in `DealStatusService`; write-path enforcement should use a trusted auth role once auth dependencies exist.
No `public` schema objects are created or modified.
```

---

## Phase 2: Iron Bank Enum Reference System

### Task 5: Create Reference Data Models and Migration

**Files:**
- Create: `app/iron_bank/models/reference_data.py`
- Modify: `app/iron_bank/models/__init__.py`
- Create: `migrations/versions/<revision>_add_iron_bank_enum_reference_data.py`

- [ ] **Step 1: Add SQLAlchemy models**

Create `app/iron_bank/models/reference_data.py`:

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EnumSet(Base):
    __tablename__ = "enum_sets"
    __table_args__ = (
        UniqueConstraint("code", name="uq_enum_sets_code"),
        {"schema": "iron_bank"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    options: Mapped[list["EnumOption"]] = relationship(
        "EnumOption",
        back_populates="enum_set",
        cascade="all, delete-orphan",
    )


class EnumOption(Base):
    __tablename__ = "enum_options"
    __table_args__ = (
        UniqueConstraint("enum_set_id", "key", name="uq_enum_options_set_key"),
        {"schema": "iron_bank"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enum_set_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("iron_bank.enum_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    enum_set: Mapped[EnumSet] = relationship("EnumSet", back_populates="options")
```

- [ ] **Step 2: Import models for metadata discovery**

Update `app/iron_bank/models/__init__.py`:

```python
from app.iron_bank.models.reference_data import EnumOption, EnumSet
from app.iron_bank.models.underwriting import *
```

- [ ] **Step 3: Create migration**

Add migration creating `iron_bank.enum_sets` and `iron_bank.enum_options`, with seed rows for current tag/dropdown fields only:

```python
ENUM_SETS = [
    ("market_type", "Market Type"),
    ("execution_type", "Execution Type"),
    ("seasonality", "Seasonality"),
    ("regulatory_clarity", "Regulatory Clarity"),
    ("offer_competitiveness", "Offer Competitiveness"),
    ("core_value_driver", "Core Value Driver"),
    ("cash_flow_quality", "Cash Flow Quality"),
    ("view_quality", "View Quality"),
    ("pool_type", "Pool Type"),
    ("primary_guest_avatar", "Primary Guest Avatar"),
]
```

Seed tag/dropdown option keys as stable lowercase snake_case values. Labels should preserve current FE labels such as `Mountain`, `Turnkey`, `Year Round`, `Clear`, `Moderate`, `Cash Flow`, `Excellent`, `None`, `Inground`, and `Families`.

- [ ] **Step 4: Run migration check**

Run:

```bash
alembic upgrade heads
```

Expected: new tables are created only in `iron_bank`.

- [ ] **Step 5: Commit models and migration**

```bash
git add app/iron_bank/models/reference_data.py app/iron_bank/models/__init__.py migrations/versions
git commit -m "feat: add iron bank enum reference tables"
```

### Task 6: Add Repository, Schemas, Service, and Endpoint

**Files:**
- Create: `app/iron_bank/schemas/reference_data.py`
- Create: `app/iron_bank/repositories/reference_data_repository.py`
- Create: `app/iron_bank/services/reference_data_service.py`
- Create: `app/iron_bank/controllers/reference_data_controller.py`
- Modify: `app/iron_bank/router.py`
- Test: `tests/iron_bank/test_reference_data_service.py`
- Test: `tests/iron_bank/test_reference_data_controller.py`

- [ ] **Step 1: Add service tests**

Create tests that verify grouped output and validation:

```python
import pytest

from app.iron_bank.services.reference_data_service import ReferenceDataService


class FakeReferenceDataRepository:
    async def list_options(self, include_inactive: bool = False):
        return [
            {
                "set_code": "pool_type",
                "key": "none",
                "label": "None",
                "sort_order": 10,
                "is_active": True,
                "is_default": True,
                "metadata": None,
            },
            {
                "set_code": "pool_type",
                "key": "inground",
                "label": "Inground",
                "sort_order": 20,
                "is_active": True,
                "is_default": False,
                "metadata": {"color": "blue"},
            },
        ]


@pytest.mark.asyncio
async def test_get_underwriting_reference_data_groups_options():
    service = ReferenceDataService(FakeReferenceDataRepository())

    result = await service.get_underwriting_reference_data()

    assert result.options["pool_type"][0].key == "none"
    assert result.options["pool_type"][1].metadata == {"color": "blue"}


@pytest.mark.asyncio
async def test_validate_active_option_rejects_unknown_key():
    service = ReferenceDataService(FakeReferenceDataRepository())

    with pytest.raises(ValueError, match="Invalid pool_type"):
        await service.validate_active_option("pool_type", "not_real")
```

- [ ] **Step 2: Add schemas**

Create `app/iron_bank/schemas/reference_data.py`:

```python
from pydantic import BaseModel, Field


class ReferenceDataOption(BaseModel):
    key: str
    label: str
    sort_order: int
    is_active: bool
    is_default: bool
    metadata: dict | None = None


class UnderwritingReferenceDataResult(BaseModel):
    options: dict[str, list[ReferenceDataOption]] = Field(default_factory=dict)
```

- [ ] **Step 3: Add repository**

Create `app/iron_bank/repositories/reference_data_repository.py` with an async query joining `EnumSet` to `EnumOption`, ordered by set code and `sort_order`.

- [ ] **Step 4: Add service**

Create `app/iron_bank/services/reference_data_service.py`:

```python
from app.iron_bank.schemas.reference_data import (
    ReferenceDataOption,
    UnderwritingReferenceDataResult,
)


class ReferenceDataService:
    def __init__(self, repository):
        self.repository = repository
        self._cache: UnderwritingReferenceDataResult | None = None

    async def get_underwriting_reference_data(self) -> UnderwritingReferenceDataResult:
        if self._cache is not None:
            return self._cache

        rows = await self.repository.list_options(include_inactive=False)
        grouped: dict[str, list[ReferenceDataOption]] = {}
        for row in rows:
            grouped.setdefault(row["set_code"], []).append(
                ReferenceDataOption(
                    key=row["key"],
                    label=row["label"],
                    sort_order=row["sort_order"],
                    is_active=row["is_active"],
                    is_default=row["is_default"],
                    metadata=row["metadata"],
                )
            )

        self._cache = UnderwritingReferenceDataResult(options=grouped)
        return self._cache

    async def validate_active_option(self, set_code: str, key: str | None) -> None:
        if key is None:
            return

        data = await self.get_underwriting_reference_data()
        valid_keys = {option.key for option in data.options.get(set_code, [])}
        if key not in valid_keys:
            raise ValueError(f"Invalid {set_code}: {key}")
```

- [ ] **Step 5: Add controller and route**

Expose:

```text
GET /iron-bank/reference-data/underwritings
```

Return `UnderwritingReferenceDataResult`.

- [ ] **Step 6: Run tests**

Run:

```bash
pytest tests/iron_bank/test_reference_data_service.py tests/iron_bank/test_reference_data_controller.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit endpoint**

```bash
git add app/iron_bank/schemas/reference_data.py app/iron_bank/repositories/reference_data_repository.py app/iron_bank/services/reference_data_service.py app/iron_bank/controllers/reference_data_controller.py app/iron_bank/router.py tests/iron_bank/test_reference_data_service.py tests/iron_bank/test_reference_data_controller.py
git commit -m "feat: expose iron bank reference data"
```

### Task 7: Convert Tag-Like Fields to DB-Validated Strings

**Files:**
- Modify: `app/iron_bank/schemas/underwriting.py`
- Modify: `app/iron_bank/schemas/update_underwriting.py`
- Modify: `app/iron_bank/services/save_underwriting_service.py`
- Modify: `app/iron_bank/services/update_underwriting_service.py`
- Test: `tests/iron_bank/test_save_underwriting_service.py`
- Test: `tests/iron_bank/test_update_underwriting_service.py`

- [ ] **Step 1: Define tag-like field mapping**

Use this mapping in the service layer:

```python
REFERENCE_DATA_FIELDS = {
    "market_type": "market_type",
    "execution_type": "execution_type",
    "seasonality": "seasonality",
    "regulatory_clarity": "regulatory_clarity",
    "offer_competitiveness": "offer_competitiveness",
    "core_value_driver": "core_value_driver",
    "cash_flow_quality": "cash_flow_quality",
    "view_quality": "view_quality",
    "pool_type": "pool_type",
    "primary_guest_avatar": "primary_guest_avatar",
}
```

- [ ] **Step 2: Add failing service validation tests**

Use a fake reference-data validator that records calls and raises for bad keys.

Expected assertions:

```python
assert validator.calls == [("pool_type", "inground")]
```

and:

```python
with pytest.raises(ValueError, match="Invalid pool_type"):
    await service.save(payload)
```

- [ ] **Step 3: Convert schemas**

In `app/iron_bank/schemas/underwriting.py`, remove the tag enum classes and type these fields as strings:

```python
market_type: str | None = None
execution_type: str | None = None
seasonality: str | None = None
regulatory_clarity: str | None = None
offer_competitiveness: str | None = None
core_value_driver: str | None = None
cash_flow_quality: str | None = None
view_quality: str | None = None
pool_type: str | None = None
primary_guest_avatar: str | None = None
```

Apply the same to `app/iron_bank/schemas/update_underwriting.py`.

- [ ] **Step 4: Inject reference-data service into save/update services**

Add optional constructor dependency:

```python
reference_data_service: ReferenceDataValidator | None = None
```

Define protocol:

```python
class ReferenceDataValidator(Protocol):
    async def validate_active_option(self, set_code: str, key: str | None) -> None: ...
```

- [ ] **Step 5: Validate fields before persistence**

Before repository create/update, run:

```python
async def _validate_reference_data_fields(self, underwriting_data: dict[str, Any]) -> None:
    if self.reference_data_service is None:
        return

    for field, set_code in REFERENCE_DATA_FIELDS.items():
        if field in underwriting_data:
            await self.reference_data_service.validate_active_option(
                set_code,
                underwriting_data[field],
            )
```

Call this method from both `save()` and `update()`.

- [ ] **Step 6: Wire reference-data service in router dependencies**

In `app/iron_bank/router.py`, build `ReferenceDataRepository(db)` and `ReferenceDataService(...)` for save/update controller construction.

- [ ] **Step 7: Run focused service tests**

Run:

```bash
pytest tests/iron_bank/test_save_underwriting_service.py tests/iron_bank/test_update_underwriting_service.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit validation**

```bash
git add app/iron_bank/schemas/underwriting.py app/iron_bank/schemas/update_underwriting.py app/iron_bank/services/save_underwriting_service.py app/iron_bank/services/update_underwriting_service.py app/iron_bank/router.py tests/iron_bank/test_save_underwriting_service.py tests/iron_bank/test_update_underwriting_service.py
git commit -m "feat: validate underwriting reference fields"
```

### Phase 2 Verification

- [ ] Run:

```bash
pytest tests/iron_bank -v
```

- [ ] Run:

```bash
alembic upgrade heads
```

- [ ] Confirm:

```text
GET /iron-bank/reference-data/underwritings returns all underwriting dropdown/tag options.
Tag-like fields accept stable DB keys.
Invalid active option keys fail before persistence.
Inactive options are not offered to FE.
Existing historical values can remain readable if their option rows are kept inactive rather than deleted.
```

---

## Rollout Notes

- Phase 1 can ship independently and immediately improves `deal_status`.
- Phase 2 should coordinate with FE because tag values will move from display labels like `Mountain` to stable keys like `mountain`.
- If existing DB rows contain display labels, add a data migration in Phase 2 to convert current labels to stable keys before service validation becomes mandatory.
- Do not use PostgreSQL native `ENUM`.
- Do not create or modify anything in the `public` schema.

## Self-Review

- Spec coverage: Phase 1 covers `deal_status` enum typing, FE discovery, transition rules, role-filtered transition previews, and DB constraint. Phase 2 covers DB-backed enum infrastructure for tag/dropdown fields, FE reference-data endpoint, service validation, and migration seeding.
- Placeholder scan: No `TBD` or unspecified implementation slots remain. Migration revision IDs are intentionally left to Alembic because they must be generated at execution time.
- Type consistency: `DealStatus` remains code-owned workflow state. Tag-like fields are strings validated by `ReferenceDataService`.
