# Batch Prepare Underwritings by Market API

This document explains how the API endpoint
`POST /iron-bank/underwritings/batch-prepare-by-market` runs end to end: request
validation, controller/job call order, how properties are selected for a market,
how each selected `zpid` becomes a draft underwriting, and what the final API
response means.

This API is the HTTP-triggered, market-scoped variant of the automated
underwriting creation workflow.

## Endpoint

```http
POST /iron-bank/underwritings/batch-prepare-by-market
```

The route is registered in `app/iron_bank/router.py` under the `/iron-bank`
router prefix.

## Request parameters

All inputs are query parameters:

| Parameter | Required | Validation | Meaning |
|---|---:|---|---|
| `market_id` | Yes | integer | Market ID used to filter scheduled presets/listings |
| `since_hours` | Yes | integer, `>= 1` | Lookback window for scheduled listing `created_at` |
| `limit` | No | integer, `>= 1` when provided | Optional maximum number of matching listings to process |

Example:

```bash
curl -X POST "http://localhost:8000/iron-bank/underwritings/batch-prepare-by-market?market_id=12&since_hours=2&limit=50"
```

Without `limit`:

```bash
curl -X POST "http://localhost:8000/iron-bank/underwritings/batch-prepare-by-market?market_id=12&since_hours=2"
```

FastAPI performs the query parameter validation before the controller is called.
Invalid or missing query parameters return FastAPI validation errors instead of
running the workflow.

## High-level flow

```text
POST /iron-bank/underwritings/batch-prepare-by-market
  -> app.iron_bank.router.batch_prepare_underwritings_by_market(...)
    -> get_workflow_trigger_controller(db)
      -> WorkflowTriggerController(
           BatchPrepareAndSaveUnderwritingsByMarketJob.from_session(db)
         )
    -> WorkflowTriggerController.batch_prepare_by_market(...)
      -> BatchPrepareAndSaveUnderwritingsByMarketJob.run(...)
        -> ScheduledListingsService.get_active_since_by_market(...)
          -> ScheduledListingsRepository.get_active_since_by_market(...)
        -> for each selected listing.zpid:
          -> PrepareAndSaveUnderwritingJob.run(zpid)
            -> UnderwritingRepository.get_by_zpid(zpid)
            -> PrepareUwDataJob.run(zpid)
            -> UnderwritingPayloadBuilder.build(prepared)
            -> SaveUnderwritingService.save(payload)
              -> UnderwritingRepository.create(...)
      -> BatchPrepareUwByMarketResult.model_validate(result)
  -> JSON response
```

## Step 1: Route and dependency wiring

The route function is:

```python
batch_prepare_underwritings_by_market(...)
```

in `app/iron_bank/router.py`.

It receives:

- `market_id`
- `since_hours`
- `limit`
- `WorkflowTriggerController`, injected by `Depends(get_workflow_trigger_controller)`

`get_workflow_trigger_controller(db)` creates:

```python
WorkflowTriggerController(
    batch_prepare_by_market_job=
        BatchPrepareAndSaveUnderwritingsByMarketJob.from_session(db)
)
```

The DB session comes from the shared `get_db` dependency.

## Step 2: Controller execution and error handling

The route calls:

```python
WorkflowTriggerController.batch_prepare_by_market(
    market_id=market_id,
    since_hours=since_hours,
    limit=limit,
)
```

The controller calls the workflow job:

```python
BatchPrepareAndSaveUnderwritingsByMarketJob.run(
    market_id=market_id,
    since_hours=since_hours,
    limit=limit,
)
```

Then it validates the returned dictionary into:

```python
BatchPrepareUwByMarketResult
```

If the job raises an exception that escapes the per-listing handling, the
controller logs:

```text
iron_bank.workflow_trigger.batch_prepare_by_market.error
```

with `market_id`, `since_hours`, `limit`, and `error`, then returns HTTP `500`:

```json
{
  "detail": "Failed to prepare and save underwritings for market"
}
```

Normal per-listing failures do not make the endpoint return `500`; they are
included in the successful response as `status: "failed"` result items.

## Step 3: Build the by-market job dependencies

`BatchPrepareAndSaveUnderwritingsByMarketJob.from_session(db)` creates:

- `ScheduledListingsService(ScheduledListingsRepository(db))`
- `PrepareAndSaveUnderwritingJob.from_session(db)`

`PrepareAndSaveUnderwritingJob.from_session(db)` creates the single-property
workflow dependencies:

- `PrepareUwDataJob.from_session(db)`
- `UnderwritingPayloadBuilder()`
- `SaveUnderwritingService(...)`
- `UnderwritingRepository(db)`

The save service is configured with:

- `UnderwritingRepository`
- `MarketService(MarketRepository)`
- `ScheduledListingsService(ScheduledListingsRepository)`
- `CleanedDataService(CleanedDataRepository)`

Those services allow save-time enrichment, including `property_pending` and
forecasted revenue when enough market/Airbnb data exists.

## Step 4: Select market listings to underwrite

The by-market job calls:

```python
ScheduledListingsService.get_active_since_by_market(
    market_id=market_id,
    since_hours=since_hours,
    limit=limit,
)
```

The service delegates directly to:

```python
ScheduledListingsRepository.get_active_since_by_market(...)
```

The repository query selects scheduled listings by joining:

```text
ScheduledListing.preset_id -> ScheduledPreset.id
```

and filtering:

- `ScheduledPreset.market_id == market_id`
- `ScheduledListing.keep_updated is True`
- `ScheduledListing.remove_listing is False`
- `ScheduledListing.created_at >= server_now_utc - since_hours`

It orders rows by:

1. `ScheduledListing.created_at desc`
2. `ScheduledListing.zpid`

If `limit` is provided, the query applies that limit.

Important: this selector runs by `market_id`, not by `preset_id`. If multiple
scheduled presets share the same market, the endpoint can process listings from
all of those presets as long as they match the active/recent filters.

Also important: this selector does not check `passes_preset_filters`. The
current rule is "recent active scheduled listings in this market", where active
means `keep_updated=true` and `remove_listing=false`.

## Step 5: Process each selected listing

For every listing returned by `get_active_since_by_market()`, the by-market job
calls:

```python
PrepareAndSaveUnderwritingJob.run(listing.zpid)
```

The by-market job catches exceptions per listing. If one `zpid` fails, the job
adds a failed result for that `zpid` and continues processing the rest.

## Step 6: Skip if an underwriting already exists

The single-property job starts with:

```python
UnderwritingRepository.get_by_zpid(zpid)
```

`get_by_zpid()` queries `iron_bank.underwritings` by `zpid`, eager-loads child
records, orders by newest underwriting ID first, and returns the latest match.

If an underwriting already exists, no new underwriting is created. The result is:

```json
{
  "zpid": "123",
  "status": "skipped_existing",
  "underwriting_id": 456
}
```

## Step 7: Prepare underwriting source data

If no underwriting exists for the `zpid`, the single-property workflow calls:

```python
PrepareUwDataJob.run(zpid)
```

That job loads the scheduled listing:

```python
ScheduledListingsService.get_by_zpid(zpid)
  -> ScheduledListingsRepository.get_by_zpid(zpid)
```

The repository joined-loads the listing's preset so the workflow can resolve
`listing.preset.market_id`.

Then the workflow gathers supporting data:

| Data | Service method | Repository method or source |
|---|---|---|
| Market | `MarketService.get_by_id(market_id)` | `MarketRepository.get_by_id(market_id)` |
| Zillow listing details | `ScheduledListingDetailsService.get_by_zpid(zpid)` | `ScheduledListingDetailsRepository.get_by_zpid(zpid)` |
| Opex by bedrooms | `OpexByBedroomsService.get_by_market_and_bedrooms(...)` | `OpexByBedroomsRepository.get_by_market_and_bedrooms(...)` |
| Opex by size | `OpexBySizeService.get_by_market_and_sqft(...)` | `OpexBySizeRepository.get_by_market_and_sqft(...)` |
| Construction amenities | `ConstructionAmenitiesService.get_all()` | `ConstructionAmenitiesRepository.get_all()` |
| Construction remodeling | `ConstructionRemodelingService.get_all()` | `ConstructionRemodelingRepository.get_all()` |
| 30-year fixed rate | `ExternalApiService.get_30y_fixed_rate()` | FRED API |

`PrepareUwDataService.prepare(...)` shapes that data into `PrepareUwDataResult`.

## Step 8: Build and validate the save payload

The workflow calls:

```python
UnderwritingPayloadBuilder.build(prepared)
```

The automated payload includes:

- `zpid`
- `market_id`
- `deal_status = TEMPLATE_GENERATED`
- `is_automated = True`
- `listing_url`
- `property_address`
- `details`
- `taxes`, when purchase price exists
- `operating_expenses`

Purchase price is normalized from the prepared Zillow property price. If there
is no usable purchase price, the workflow does not save anything and returns:

```json
{
  "zpid": "123",
  "status": "skipped_no_purchase_price"
}
```

## Step 9: Save the draft underwriting

When the payload has a purchase price, the workflow calls:

```python
SaveUnderwritingService.save(payload)
```

The save service:

1. Splits parent underwriting fields from child fields.
2. Applies `property_pending` from scheduled listing `home_status`.
3. Builds tax data with `UnderwritingCalculator.calculate_taxes(...)`.
4. Resolves bedrooms for forecasted revenue lookup.
5. Builds detail data, including purchase details and forecasted revenue when possible.
6. Calculates parent summary metrics such as `purchase_price`, `total_oop`,
   `prr`, `budget_to_pp`, and cash-on-cash values when enough inputs exist.
7. Calls `UnderwritingRepository.create(...)`.

The repository creates:

- parent `Underwriting`
- `UnderwritingDetail`, when detail data exists
- `UnderwritingTax`, when tax data exists
- `UnderwritingOptimizationItem` rows
- `UnderwritingOperatingExpense` rows
- `UnderwritingCompSet` rows

It commits the transaction and returns the new underwriting. The successful
per-listing result is:

```json
{
  "zpid": "123",
  "status": "saved",
  "underwriting_id": 456
}
```

## Final API response

The endpoint returns `BatchPrepareUwByMarketResult`:

```json
{
  "market_id": 12,
  "found": 4,
  "processed": 4,
  "saved": 1,
  "skipped_existing": 1,
  "skipped_no_purchase_price": 1,
  "failed": 1,
  "results": [
    {
      "zpid": "1",
      "status": "saved",
      "underwriting_id": 10
    },
    {
      "zpid": "2",
      "status": "skipped_existing",
      "underwriting_id": 20
    },
    {
      "zpid": "3",
      "status": "failed",
      "error": "boom"
    },
    {
      "zpid": "4",
      "status": "skipped_no_purchase_price"
    }
  ]
}
```

Field meanings:

| Field | Meaning |
|---|---|
| `market_id` | Market ID passed to the endpoint |
| `found` | Number of scheduled listings selected by the market/time query |
| `processed` | Number of per-listing results produced |
| `saved` | Count of new draft underwritings created |
| `skipped_existing` | Count skipped because an underwriting already exists for the `zpid` |
| `skipped_no_purchase_price` | Count skipped because no usable purchase price was available |
| `failed` | Count that raised an exception during per-listing processing |
| `results` | Ordered per-`zpid` results matching processing order |

## Status values

| Status | Produced by | Meaning |
|---|---|---|
| `saved` | `PrepareAndSaveUnderwritingJob.run()` | A new draft underwriting was created |
| `skipped_existing` | `PrepareAndSaveUnderwritingJob.run()` | An underwriting already exists for that `zpid` |
| `skipped_no_purchase_price` | `PrepareAndSaveUnderwritingJob.run()` | The listing did not provide a usable purchase price |
| `failed` | `BatchPrepareAndSaveUnderwritingsByMarketJob.run()` | An exception occurred for that `zpid`; the batch continued |

## Code map

| Responsibility | File |
|---|---|
| API route and query validation | `app/iron_bank/router.py` |
| Controller and HTTP 500 handling | `app/iron_bank/controllers/workflow_trigger_controller.py` |
| API response schema | `app/iron_bank/schemas/batch_prepare_uw.py` |
| Market-scoped batch job | `app/workflows/batch_prepare_and_save_underwritings_by_market_job.py` |
| Single-property prepare/save job | `app/workflows/prepare_and_save_underwriting_job.py` |
| Cross-domain prepared data job | `app/workflows/prepare_uw_data_job.py` |
| Prepared data shaping | `app/iron_bank/services/prepare_uw_data_service.py` |
| Automated save payload builder | `app/iron_bank/services/underwriting_payload_builder.py` |
| Save-time calculations and persistence orchestration | `app/iron_bank/services/save_underwriting_service.py` |
| Underwriting DB writes | `app/iron_bank/repositories/underwriting_repository.py` |
| Market-scoped listing selection | `app/zillow/repositories/scheduled_listings_repository.py` |

## Notes and caveats

- The endpoint runs only the creation workflow. It does not run purchase-price
  reconciliation.
- The selector uses scheduled listing `created_at`, not listing details
  `price_change_date`.
- The selector is market-scoped, not preset-scoped.
- The selector does not check `passes_preset_filters`.
- Missing purchase price skips a listing.
- Missing optional market, opex, construction, FRED, or Airbnb percentile data
  may leave optional fields empty but does not necessarily block saving.
- Per-listing exceptions are returned in `results` with `status: "failed"`;
  uncaught job/controller-level exceptions return HTTP `500`.
