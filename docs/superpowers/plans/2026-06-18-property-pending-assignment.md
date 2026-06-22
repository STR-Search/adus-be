# Property Pending Assignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assign `Underwriting.property_pending` from `ScheduledListing.home_status` whenever an underwriting is saved.

**Architecture:** `SaveUnderwritingService` will keep financial calculations and listing-derived booleans separate. A dedicated asynchronous helper will look up the scheduled listing through the existing listing service and write `property_pending` into `underwriting_data`; absent listing infrastructure, a missing listing, or a missing `zpid` will leave existing payload behavior unchanged.

**Tech Stack:** Python 3, FastAPI service layer, Pydantic, pytest/pytest-asyncio

---

## File Structure

- Modify `tests/iron_bank/test_save_underwriting_service.py` to make the listing fake expose `home_status` and add status-mapping regression coverage.
- Modify `app/iron_bank/services/save_underwriting_service.py` to call a dedicated listing-boolean helper before repository persistence.

### Task 1: Add Property-Pending Mapping

**Files:**
- Modify: `tests/iron_bank/test_save_underwriting_service.py`
- Modify: `app/iron_bank/services/save_underwriting_service.py`

- [ ] **Step 1: Write the failing parameterized service test**

Update the listing fake and add the mapping test:

```python
class FakeListingsService:
    def __init__(self, beds=4, home_status=None):
        self.beds = beds
        self.home_status = home_status
        self.zpid = None

    async def get_by_zpid(self, zpid: str):
        self.zpid = zpid
        return SimpleNamespace(beds=self.beds, home_status=self.home_status)


@pytest.mark.parametrize(
    ("home_status", "expected_property_pending"),
    [
        (None, False),
        ("FOR_SALE", False),
        ("SOLD", True),
        ("OTHER", True),
        ("RECENTLY_SOLD", True),
        ("PENDING", True),
    ],
)
@pytest.mark.asyncio
async def test_save_assigns_property_pending_from_listing_home_status(
    home_status, expected_property_pending
):
    repository = FakeUnderwritingRepository()
    service = SaveUnderwritingService(
        repository,
        listings_service=FakeListingsService(home_status=home_status),
    )
    payload = SaveUnderwritingPayload.model_validate({"zpid": "12345"})

    await service.save(payload)

    assert repository.underwriting_data["property_pending"] is expected_property_pending
```

- [ ] **Step 2: Run the test and verify it fails for the missing assignment**

Run:

```bash
pytest tests/iron_bank/test_save_underwriting_service.py::test_save_assigns_property_pending_from_listing_home_status -v
```

Expected: failures showing that `underwriting_data["property_pending"]` does not match the listing-derived values, with at least the non-`FOR_SALE` cases failing.

- [ ] **Step 3: Implement the dedicated helper and call it from `save()`**

In `SaveUnderwritingService.save()`, invoke the helper after constructing `underwriting_data` and before repository creation:

```python
await self._apply_listing_boolean_fields(underwriting_data, payload)
```

Add the helper:

```python
async def _apply_listing_boolean_fields(
    self,
    underwriting_data: dict[str, Any],
    payload: SaveUnderwritingPayload,
) -> None:
    if self.listings_service is None or payload.zpid is None:
        return

    listing = await self.listings_service.get_by_zpid(payload.zpid)
    if listing is None:
        return

    underwriting_data["property_pending"] = listing.home_status not in (
        None,
        "FOR_SALE",
    )
```

- [ ] **Step 4: Run the focused test and verify all mappings pass**

Run:

```bash
pytest tests/iron_bank/test_save_underwriting_service.py::test_save_assigns_property_pending_from_listing_home_status -v
```

Expected: `6 passed`.

- [ ] **Step 5: Run the complete save-service test module**

Run:

```bash
pytest tests/iron_bank/test_save_underwriting_service.py -v
```

Expected: all tests pass with no failures or errors.

- [ ] **Step 6: Run the project test suite**

Run:

```bash
pytest
```

Expected: all tests pass with no failures or errors.

- [ ] **Step 7: Review the diff and commit only the implementation files**

Run:

```bash
git diff --check
git diff -- tests/iron_bank/test_save_underwriting_service.py app/iron_bank/services/save_underwriting_service.py
git add tests/iron_bank/test_save_underwriting_service.py app/iron_bank/services/save_underwriting_service.py
git commit -m "feat: derive property pending from listing status"
```

Expected: the diff contains only the status mapping, dedicated helper, and regression test; the commit succeeds without including unrelated workspace changes.
