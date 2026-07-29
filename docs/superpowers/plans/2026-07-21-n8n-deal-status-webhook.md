# n8n Deal-Status Webhook Implementation Plan

**Goal:** When an underwriting moves to `present_to_clients`, POST that underwriting's row to an n8n webhook so downstream automation can react. Today a status change is invisible outside Postgres — a human has to go look.

**Scope:** `present_to_clients` only. `analyst_completed` gets a second `if` block in a later PR once its n8n workflow exists.

**Architecture:** Two pieces plus wiring.

| Concern | Home | Rationale |
|---|---|---|
| HTTP transport | `app/external_api/services/n8n_webhook_service.py` | Outbound third-party HTTP is what `external_api` is for; mirrors `ZillowPropertyService` |
| Call site | `app/iron_bank/services/update_underwriting_service.py` | The only method that mutates `deal_status` |
| Wiring | `app/iron_bank/router.py` | Composition root; function-local import preserves the no-cross-domain-import rule |

The client is an optional constructor dependency defaulting to `None`, like `listings_service` and `reference_data_service`. That is the off switch: `ReconcileUnderwritingPriceJob.from_session` builds `UpdateUnderwritingService` bare, so machine-driven price reconciliation can never fire a client-facing automation.

**Tech Stack:** FastAPI, Pydantic v2, httpx, structlog, pytest + pytest-asyncio. No migration, no new schema file — nothing schema-side changes.

---

## Decisions

Settled before writing this; recorded so PR review has the context.

1. **Payload = the parent row.** The ~60 columns of `iron_bank.underwritings`, serialized through the existing `UnderwritingRead` schema. Not the child tables, not the full GET response.
2. **Fire after the commit**, keeping the `if deal_status == DealStatus.PRESENT_TO_CLIENTS:` branch structure. A webhook is an irreversible external side effect — it must not announce a change that failed to persist.
3. **`present_to_clients` only** in this PR.
4. **No auth yet.** Built with a `_headers()` seam so a shared secret can be added later without touching the call site.

---

## File Structure

- Create: `app/external_api/services/n8n_webhook_service.py`
  - `N8nWebhookService.send()` — POSTs a JSON body, never raises.
- Modify: `app/core/config.py`
  - Adds `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_ENABLED`, `N8N_WEBHOOK_TIMEOUT_SECONDS`.
- Modify: `.env.example`
  - Documents the vars and the test-vs-prod URL difference.
- Modify: `app/iron_bank/services/update_underwriting_service.py`
  - Accepts `n8n_webhook_service`; fires in `update_deal_status` after the commit.
- Modify: `app/iron_bank/router.py`
  - Injects `N8nWebhookService()` in `get_update_underwriting_controller`.
- Test: `tests/external_api/test_n8n_webhook_service.py`
  - Disabled/unconfigured short-circuit, success, swallowed failure.
- Test: `tests/iron_bank/test_update_underwriting_service.py`
  - Fires on `present_to_clients`, silent on others, silent on no-op re-PATCH, sends the full row, and a webhook failure does not fail the update.

**Not touched:** `deal_status_service.py` stays as-is. With one status in scope, a plain `if` is clearer than a lookup table. If a third status ever needs an automation, revisit then.

---

## Task 1: Config and env vars

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add settings**

In `app/core/config.py`, after the Sentry block:

```python
    # n8n automation webhook, fired when an underwriting reaches
    # present_to_clients. n8n distinguishes environments by URL path
    # (/webhook-test/<uuid> vs /webhook/<uuid>, same uuid), so this is set per
    # environment rather than branched on APP_ENV in code.
    N8N_WEBHOOK_URL: str = ""
    N8N_WEBHOOK_ENABLED: bool = False
    N8N_WEBHOOK_TIMEOUT_SECONDS: int = 10
```

`N8N_WEBHOOK_ENABLED` defaults to `False` so no environment starts firing by surprise — including local dev and CI.

- [ ] **Step 2: Document in `.env.example`**

```bash
# n8n automation webhook (fired on deal_status -> present_to_clients)
# Production: https://n8n-strsearch.onrender.com/webhook/<uuid>        ALWAYS LIVE
# Test:      https://n8n-strsearch.onrender.com/webhook-test/<uuid>    needs arming
N8N_WEBHOOK_ENABLED=false
N8N_WEBHOOK_URL=https://n8n-strsearch.onrender.com/webhook/4ef3cb3c-dafa-4667-97ba-c558135ec0f4
N8N_WEBHOOK_TIMEOUT_SECONDS=10
```

> **The workflow moved to the production URL on 2026-07-21** (same uuid, `/webhook/` instead of `/webhook-test/`). Two consequences:
>
> - No more arming. The production endpoint is always listening, so "Listen for test event" is no longer needed.
> - **Every fire is real.** Test events now run the live workflow and whatever it does downstream. Confirm with the workflow owner that its actions are safe to trigger repeatedly before using real underwritings.
>
> The test URL still works for dry runs, but only while armed in the n8n editor.

---

## Task 2: The webhook client

**Files:**
- Create: `app/external_api/services/n8n_webhook_service.py`
- Test: `tests/external_api/test_n8n_webhook_service.py`

- [ ] **Step 1: Add failing tests**

Create `tests/external_api/test_n8n_webhook_service.py`:

```python
import pytest

from app.external_api.services.n8n_webhook_service import N8nWebhookService


@pytest.mark.asyncio
async def test_send_short_circuits_when_disabled():
    service = N8nWebhookService(url="https://example.test/hook", enabled=False)

    assert await service.send(payload={"id": 1}) is False


@pytest.mark.asyncio
async def test_send_short_circuits_when_url_missing():
    service = N8nWebhookService(url="", enabled=True)

    assert await service.send(payload={"id": 1}) is False


@pytest.mark.asyncio
async def test_send_returns_false_and_does_not_raise_on_transport_error(monkeypatch):
    service = N8nWebhookService(url="https://example.test/hook", enabled=True)

    async def boom(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(service, "_post", boom)

    assert await service.send(payload={"id": 1}) is False
```

- [ ] **Step 2: Run and verify failure**

```bash
pytest tests/external_api/test_n8n_webhook_service.py -v
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

Create `app/external_api/services/n8n_webhook_service.py`:

```python
import asyncio
from typing import Any

import httpx
import structlog

from app.core.config import get_config

logger = structlog.get_logger(__name__)

# One retry, not the three used elsewhere in external_api. Those clients fetch
# data we need; this one announces an event that already happened. A retry
# covers a transient connection blip, but every extra attempt is another chance
# to deliver twice if n8n accepted and the response was lost. Worst case this
# adds ~20s to the PATCH — see the latency note in the plan.
_MAX_ATTEMPTS = 2


class N8nWebhookService:
    """Fire-and-forget client for the n8n automation webhook.

    Never raises: the DB write it reports has already committed, so a failure
    here must not surface to the caller. Returns whether n8n accepted the
    event, for logging and tests.
    """

    def __init__(
        self,
        url: str | None = None,
        enabled: bool | None = None,
        timeout_seconds: int | None = None,
    ):
        config = get_config()
        self.url = config.N8N_WEBHOOK_URL if url is None else url
        self.enabled = config.N8N_WEBHOOK_ENABLED if enabled is None else enabled
        self.timeout_seconds = (
            config.N8N_WEBHOOK_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )

    async def send(self, *, payload: dict[str, Any]) -> bool:
        if not self.enabled:
            logger.debug("external_api.n8n_webhook.disabled")
            return False
        if not self.url:
            logger.warning(
                "external_api.n8n_webhook.not_configured",
                detail="N8N_WEBHOOK_ENABLED is true but N8N_WEBHOOK_URL is empty",
            )
            return False

        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = await self._post(payload)
                if 200 <= response.status_code < 300:
                    logger.info(
                        "external_api.n8n_webhook.sent",
                        status_code=response.status_code,
                        underwriting_id=payload.get("id"),
                    )
                    return True
                logger.warning(
                    "external_api.n8n_webhook.rejected",
                    status_code=response.status_code,
                    underwriting_id=payload.get("id"),
                    attempt=attempt,
                )
            except Exception as exc:
                logger.warning(
                    "external_api.n8n_webhook.error",
                    error=str(exc),
                    underwriting_id=payload.get("id"),
                    attempt=attempt,
                )
            await asyncio.sleep(0.4 + attempt * 0.4)

        logger.error(
            "external_api.n8n_webhook.exhausted",
            underwriting_id=payload.get("id"),
        )
        return False

    def _headers(self) -> dict[str, str]:
        """Outbound headers. Auth seam — when n8n needs a shared secret, add
        N8N_WEBHOOK_TOKEN to config and return it here. No call site changes."""
        return {"Content-Type": "application/json"}

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            return await client.post(self.url, json=payload, headers=self._headers())
```

Constructor args override config so tests never touch env.

- [ ] **Step 4: Run tests**

```bash
pytest tests/external_api/test_n8n_webhook_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/external_api/services/n8n_webhook_service.py app/core/config.py .env.example tests/external_api/test_n8n_webhook_service.py
git commit -m "feat: add n8n webhook client and config"
```

---

## Task 3: Fire from `update_deal_status`

**Files:**
- Modify: `app/iron_bank/services/update_underwriting_service.py`
- Test: `tests/iron_bank/test_update_underwriting_service.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/iron_bank/test_update_underwriting_service.py`:

```python
class FakeN8nWebhookService:
    def __init__(self, fail: bool = False):
        self.payloads = []
        self.fail = fail

    async def send(self, *, payload: dict) -> bool:
        if self.fail:
            raise RuntimeError("n8n unreachable")
        self.payloads.append(payload)
        return True


def _underwriting(**overrides):
    base = dict(
        id=42,
        zpid="2078451",
        market_id=7,
        analyst_id=3,
        approver_id=None,
        deal_status=DealStatus.ANALYST_COMPLETED,
        property_address="1 Main St, Austin, TX",
        listing_url="https://zillow.com/x",
        purchase_price=Decimal("525000.00"),
        total_oop=Decimal("182500.00"),
        luxury=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_update_deal_status_fires_webhook_on_present_to_clients():
    webhook = FakeN8nWebhookService()
    repository = FakeUnderwritingRepository(_underwriting())
    service = UpdateUnderwritingService(repository, n8n_webhook_service=webhook)

    await service.update_deal_status(
        underwriting_id=42,
        deal_status=DealStatus.PRESENT_TO_CLIENTS,
        actor_user_id=9,
    )

    assert len(webhook.payloads) == 1
    payload = webhook.payloads[0]
    assert payload["id"] == 42
    assert payload["zpid"] == "2078451"
    assert payload["property_address"] == "1 Main St, Austin, TX"
    assert payload["purchase_price"] == "525000.00"
    assert payload["luxury"] is True


@pytest.mark.asyncio
async def test_update_deal_status_does_not_fire_for_other_statuses():
    webhook = FakeN8nWebhookService()
    repository = FakeUnderwritingRepository(_underwriting())
    service = UpdateUnderwritingService(repository, n8n_webhook_service=webhook)

    await service.update_deal_status(
        underwriting_id=42,
        deal_status=DealStatus.MAYBE,
        actor_user_id=9,
    )

    assert webhook.payloads == []


@pytest.mark.asyncio
async def test_update_deal_status_does_not_refire_when_already_present_to_clients():
    webhook = FakeN8nWebhookService()
    repository = FakeUnderwritingRepository(
        _underwriting(deal_status=DealStatus.PRESENT_TO_CLIENTS)
    )
    service = UpdateUnderwritingService(repository, n8n_webhook_service=webhook)

    await service.update_deal_status(
        underwriting_id=42,
        deal_status=DealStatus.PRESENT_TO_CLIENTS,
        actor_user_id=9,
    )

    assert webhook.payloads == []


@pytest.mark.asyncio
async def test_update_deal_status_succeeds_when_webhook_raises():
    repository = FakeUnderwritingRepository(_underwriting())
    service = UpdateUnderwritingService(
        repository, n8n_webhook_service=FakeN8nWebhookService(fail=True)
    )

    result = await service.update_deal_status(
        underwriting_id=42,
        deal_status=DealStatus.PRESENT_TO_CLIENTS,
        actor_user_id=9,
    )

    assert result.underwriting_id == 42
```

The last test is the important one: it pins the guarantee that n8n being down cannot break a status change.

> `FakeUnderwritingRepository.update` returns the object it was constructed with without applying `underwriting_data`, so the fake row's `deal_status` stays at its initial value. That is fine for these assertions. If you extend them to assert on the *returned* `deal_status`, make the fake apply the update first.

- [ ] **Step 2: Run and verify failure**

```bash
pytest tests/iron_bank/test_update_underwriting_service.py -v
```

Expected: FAIL — `n8n_webhook_service` is not a constructor arg.

- [ ] **Step 3: Add the dependency**

In `UpdateUnderwritingService.__init__`, add the parameter and store it. It does **not** go on `SaveUnderwritingService` — only the update path changes deal status:

```python
    def __init__(
        self,
        repository: UnderwritingRepository,
        calculator: UnderwritingCalculator | None = None,
        market_service=None,
        listings_service=None,
        cleaned_data_service=None,
        reference_data_service=None,
        n8n_webhook_service=None,
    ):
        super().__init__(...)  # unchanged
        self.n8n_webhook_service = n8n_webhook_service
```

- [ ] **Step 4: Fire after the commit**

`update_deal_status` keeps its existing `if` branch for the approver stamping, and gains a second one after the update lands:

```python
        existing = await self.repository.get_by_id(underwriting_id)
        if existing is None:
            raise LookupError(f"Underwriting {underwriting_id} not found")

        # Bind before repository.update. That call re-fetches through
        # SQLAlchemy's identity map and mutates this same object, so reading
        # existing.deal_status afterwards would return the NEW status.
        previous_status = existing.deal_status

        underwriting_data: dict = {"deal_status": deal_status}
        if existing.analyst_id is None:
            underwriting_data["analyst_id"] = actor_user_id
        if deal_status == DealStatus.PRESENT_TO_CLIENTS:
            underwriting_data["approver_id"] = actor_user_id
            underwriting_data["deal_approved"] = datetime.now(timezone.utc)

        await self._sync_listing_removal(existing, deal_status)

        underwriting = await self.repository.update(
            underwriting_id=underwriting_id,
            underwriting_data=underwriting_data,
        )
        if underwriting is None:
            raise LookupError(f"Underwriting {underwriting_id} not found")

        # Only now is the row committed — safe to announce it externally.
        if (
            deal_status == DealStatus.PRESENT_TO_CLIENTS
            and previous_status != DealStatus.PRESENT_TO_CLIENTS
        ):
            await self._trigger_n8n_webhook(underwriting)

        return UpdateDealStatusResult(
            underwriting_id=underwriting.id,
            deal_status=underwriting.deal_status,
        )
```

The `previous_status` guard stops a repeated PATCH (double-click, retry) from notifying clients twice about the same deal.

- [ ] **Step 5: Add the trigger method**

```python
    async def _trigger_n8n_webhook(self, underwriting) -> None:
        """POST the underwriting row to the n8n automation webhook.

        Never raises. The status write has already committed, so an n8n outage
        must not surface to the caller — it cannot be allowed to 500 an
        approver's status change.

        The body is the parent underwritings row only, serialized through
        UnderwritingRead — the same shape GetUnderwritingService returns for the
        parent, so n8n sees a field set it can also get from
        GET /iron-bank/underwritings/{id}. Child tables (details, taxes, opex,
        comps) are deliberately excluded; n8n can call back for those.
        """
        if self.n8n_webhook_service is None:
            return

        # getattr-with-default mirrors GetUnderwritingService._parent_data:
        # UnderwritingRead carries fields with no ORM column (display_id, the
        # reference *_label fields), and this avoids touching any relationship
        # attribute, which would raise MissingGreenlet under async SQLAlchemy.
        row = UnderwritingRead.model_validate(
            {
                field: getattr(underwriting, field, None)
                for field in UnderwritingRead.model_fields
            }
        )

        try:
            await self.n8n_webhook_service.send(payload=row.model_dump(mode="json"))
        except Exception:
            logger.exception(
                "iron_bank.deal_status.webhook_failed",
                underwriting_id=underwriting.id,
            )
```

Add imports: `from app.core.logger import logger` and `from app.iron_bank.schemas.underwriting import UnderwritingRead`.

`model_dump(mode="json")` serializes `Decimal` to string (`"525000.00"`, no float rounding) and `datetime` to ISO 8601. Note `jsonable_encoder` — already imported in this module — would coerce `Decimal` to float instead; prefer the Pydantic path for money.

**Two cosmetic notes on the body, for review:**
- `display_id` serializes as `null` — it has no DB column and is generated at the API layer.
- The ten reference `*_label` fields serialize as `null`. `reference_data_service` is already injected into this service, so populating them via `get_label_map` is a cheap follow-up if n8n wants human-readable tag names rather than slugs. `deal_status_label` is a computed field and **does** populate ("Present To Clients").

- [ ] **Step 6: Run tests**

```bash
pytest tests/iron_bank/test_update_underwriting_service.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/iron_bank/services/update_underwriting_service.py tests/iron_bank/test_update_underwriting_service.py
git commit -m "feat: trigger n8n webhook on present to clients"
```

---

## Task 4: Wire it into the route

**Files:**
- Modify: `app/iron_bank/router.py`

- [ ] **Step 1: Inject the client**

In `get_update_underwriting_controller` (~line 129), add to the function-local import block and pass it through:

```python
    from app.external_api.services.n8n_webhook_service import N8nWebhookService

    return UpdateUnderwritingController(
        UpdateUnderwritingService(
            UnderwritingRepository(db),
            market_service=MarketService(MarketRepository(db)),
            listings_service=ScheduledListingsService(ScheduledListingsRepository(db)),
            cleaned_data_service=CleanedDataService(CleanedDataRepository(db)),
            reference_data_service=ReferenceDataService(ReferenceDataRepository(db)),
            n8n_webhook_service=N8nWebhookService(),
        )
    )
```

Without this line the parameter stays `None` forever and the webhook silently never fires — tests would still pass. This is the only wiring site needed: `PATCH /iron-bank/underwritings/{id}/deal-status` is the sole caller of `update_deal_status`.

- [ ] **Step 2: Verify the app boots**

```bash
uvicorn main:app --reload
```

Expected: starts clean; `/docs` lists the deal-status PATCH unchanged.

- [ ] **Step 3: Commit**

```bash
git add app/iron_bank/router.py
git commit -m "feat: wire n8n webhook into deal status route"
```

---

## Verification

- [ ] Run the full suite:

```bash
pytest -v
```

- [ ] Manual end-to-end:

1. Set `N8N_WEBHOOK_ENABLED=true` and `N8N_WEBHOOK_URL=<production url>` locally. (No arming needed — the production endpoint is always live.)
2. `PATCH /iron-bank/underwritings/{id}/deal-status` with `{"deal_status": "present_to_clients"}` on a row **not** already in that status.
3. Confirm n8n receives the row and the fields the workflow reads are all present.
4. Remember this runs the live workflow — coordinate with the workflow owner first.

- [ ] Confirm:

```text
present_to_clients fires exactly one event.
No other status fires anything.
Re-sending present_to_clients on an already-present_to_clients row fires nothing.
With N8N_WEBHOOK_ENABLED=false, nothing fires and no warning is logged.
With the URL unreachable, the PATCH still returns 200 and logs a warning.
The reconcile job path fires nothing.
```

---

## Known trade-offs

**Latency.** The event is awaited inline, so a hanging n8n adds up to ~20s to the PATCH (2 attempts x 10s timeout, plus backoff). Acceptable for a low-frequency approval action. If it becomes a problem, hand it to `BackgroundTasks` the way the batch jobs do, or drop `_MAX_ATTEMPTS` to 1.

**Lost events.** No outbox or retry queue. If n8n is down for both attempts the event is gone permanently and nobody is told. Acceptable for v1; if it isn't, the fix is a durable outbox table, not more retries.

**Duplicate delivery.** A retry can double-deliver if n8n accepted but the response was lost. The `previous_status` guard prevents duplicates from repeated PATCHes, but not from a retried HTTP call. If the workflow is not idempotent, the payload's `id` + `deal_approved` timestamp form a usable idempotency key.

**Payload contains business data.** The row includes purchase price, revenue forecasts, cash-on-cash and free-text notes, POSTed unauthenticated over TLS. The webhook URL is effectively the secret. Revisit when the auth question is decided — the `_headers()` seam is there for it.

---

## Related, out of scope

`update_deal_status` **never calls `DealStatusService.validate_transition`.** The transition graph and role gating are fully built and exposed via `GET /iron-bank/deal-statuses/transitions`, but the PATCH does not enforce them — any authenticated user can jump an underwriting from `template_generated` straight to `present_to_clients`.

Today that is a data-integrity bug. Once this PR ships, it becomes an unintended *external* side effect: a bad transition no longer just writes a wrong row, it triggers client-facing work.

It is likely unwired because `validate_transition` needs an `actor_role` and `users.users` has no role column (`id`, `clerk_id`, `email`, `first_name`, `last_name`, `is_deleted`). Fixing it means deciding where roles live — Clerk claims, or a new column. Separate PR, but worth raising with the team.
