# BatchPrepareAndSaveUnderwritingsJob

This document explains how `BatchPrepareAndSaveUnderwritingsJob` decides which
properties should receive automated draft underwritings, what services and
repository methods are called, and what output the job returns.

The job is the batch wrapper around the single-property workflow
`PrepareAndSaveUnderwritingJob`. It finds recent active Zillow scheduled
listings, runs the single-property workflow for each `zpid`, and returns a
summary of saved, skipped, and failed items.

## Entry points

### CLI batch run

The main batch entry point is `scripts/run_uw_auto_prepare.py`.

When called with `--since-hours`, `run_batch()` opens an async DB session and
runs:

1. `BatchPrepareAndSaveUnderwritingsJob.from_session(session).run(...)`
2. `BatchReconcileUnderwritingPricesJob.from_session(session).run(...)`

The CLI prints a JSON object with both results:

```json
{
  "creation": { "...": "BatchPrepareAndSaveUnderwritingsJob result" },
  "price_reconciliation": { "...": "BatchReconcileUnderwritingPricesJob result" }
}
```

This document focuses on the `creation` side.

When called with `--zpid`, the script bypasses the batch selector and runs
`PrepareAndSaveUnderwritingJob` for one property.

### HTTP by-market variant

The HTTP route `POST /iron-bank/underwritings/batch-prepare-by-market` uses
`BatchPrepareAndSaveUnderwritingsByMarketJob`. That class is almost the same
wrapper, but it adds a `market_id` filter while selecting listings and includes
`market_id` in the response.

## High-level flow

```text
BatchPrepareAndSaveUnderwritingsJob.run(since_hours, limit)
  -> ScheduledListingsService.get_active_since(...)
    -> ScheduledListingsRepository.get_active_since(...)
  -> for each ScheduledListing.zpid:
    -> PrepareAndSaveUnderwritingJob.run(zpid)
      -> UnderwritingRepository.get_by_zpid(zpid)
      -> PrepareUwDataJob.run(zpid)
      -> UnderwritingPayloadBuilder.build(prepared)
      -> skip if no purchase price
      -> SaveUnderwritingService.save(payload)
        -> UnderwritingRepository.create(...)
  -> return aggregate summary and per-zpid results
```

## Step 1: Build the job dependencies

`BatchPrepareAndSaveUnderwritingsJob.from_session(db)` creates:

- `ScheduledListingsService(ScheduledListingsRepository(db))`
- `PrepareAndSaveUnderwritingJob.from_session(db)`

`PrepareAndSaveUnderwritingJob.from_session(db)` creates:

- `PrepareUwDataJob.from_session(db)`
- `UnderwritingPayloadBuilder()`
- `SaveUnderwritingService(...)`
- `UnderwritingRepository(db)`

The save service is configured with:

- `UnderwritingRepository`
- `MarketService(MarketRepository)`
- `ScheduledListingsService(ScheduledListingsRepository)`
- `CleanedDataService(CleanedDataRepository)`

Those extra services allow save-time enrichment, such as `property_pending` and
forecasted revenue.

## Step 2: Select properties to underwrite

`BatchPrepareAndSaveUnderwritingsJob.run()` receives:

- `since_hours`: required lookback window
- `limit`: optional maximum number of listings to process

It calls:

```python
ScheduledListingsService.get_active_since(
    since_hours=since_hours,
    limit=limit,
)
```

That service delegates directly to:

```python
ScheduledListingsRepository.get_active_since(...)
```

The repository query selects rows from scheduled Zillow listings where:

- `ScheduledListing.keep_updated is True`
- `ScheduledListing.remove_listing is False`
- `ScheduledListing.created_at >= server_now_utc - since_hours`

It orders the rows by:

1. `created_at desc`
2. `zpid`

If `limit` is provided, the query applies that limit.

Important: the batch selector does not check whether a listing passed preset
filters. The current selection rule is "recent active scheduled listings", where
active means `keep_updated=true` and `remove_listing=false`.

## Step 3: Process each selected listing

For every listing returned by `get_active_since()`, the batch job calls:

```python
PrepareAndSaveUnderwritingJob.run(listing.zpid)
```

The batch job catches exceptions per listing. A failure for one `zpid` becomes a
per-item result with `status: "failed"` and does not stop the rest of the batch.

## Step 4: Skip if an underwriting already exists

The single-property job starts with:

```python
UnderwritingRepository.get_by_zpid(zpid)
```

`get_by_zpid()` queries `iron_bank.underwritings` by `zpid`, eager-loads child
records, orders by newest underwriting ID first, and returns the latest match.

If it finds a row, the job stops and returns:

```json
{
  "zpid": "123",
  "status": "skipped_existing",
  "underwriting_id": 456
}
```

This is the duplicate guard. Automated batch creation assumes at most one active
underwriting should be created for a `zpid`; if one already exists, no new
underwriting is saved.

## Step 5: Prepare underwriting source data

If no existing underwriting is found, the job calls:

```python
PrepareUwDataJob.run(zpid)
```

This workflow orchestrates data reads across domains. It first loads the Zillow
scheduled listing:

```python
ScheduledListingsService.get_by_zpid(zpid)
  -> ScheduledListingsRepository.get_by_zpid(zpid)
```

`ScheduledListingsRepository.get_by_zpid()` joined-loads the scheduled preset so
the workflow can read `listing.preset.market_id`.

If no scheduled listing exists for the `zpid`, the job raises:

```text
ValueError("No listing found for the provided zpid")
```

In batch mode, that exception is caught and becomes a failed item.

After the listing is loaded, `PrepareUwDataJob.run()` derives:

- `market_id` from `listing.preset.market_id`, if a preset exists
- normalized square footage from `PrepareUwDataService.normalize_sqft(listing.area)`

The square-foot normalization buckets area into the nearest configured checkpoint:

```text
1000, 1500, 2000, 2750, 3500, 4500
```

Then it loads the rest of the data needed to assemble a draft underwriting:

| Data | Service method | Repository method or source |
|---|---|---|
| Market | `MarketService.get_by_id(market_id)` | `MarketRepository.get_by_id(market_id)` |
| Zillow listing details | `ScheduledListingDetailsService.get_by_zpid(zpid)` | `ScheduledListingDetailsRepository.get_by_zpid(zpid)` |
| Opex by bedrooms | `OpexByBedroomsService.get_by_market_and_bedrooms(...)` | `OpexByBedroomsRepository.get_by_market_and_bedrooms(...)` |
| Opex by size | `OpexBySizeService.get_by_market_and_sqft(...)` | `OpexBySizeRepository.get_by_market_and_sqft(...)` |
| Construction amenities | `ConstructionAmenitiesService.get_all()` | `ConstructionAmenitiesRepository.get_all()` |
| Construction remodeling | `ConstructionRemodelingService.get_all()` | `ConstructionRemodelingRepository.get_all()` |
| 30-year fixed rate | `ExternalApiService.get_30y_fixed_rate()` | FRED API |

Finally, the workflow calls:

```python
PrepareUwDataService.prepare(...)
```

That pure service transforms all fetched values into `PrepareUwDataResult`.

## Step 6: Shape `PrepareUwDataResult`

`PrepareUwDataService.prepare()` returns a structure containing:

- market identity: `market_name`, `market_id`, `market_slug`
- Zillow property data
- operating expense data
- construction amenity options
- construction remodeling options
- underwriting config defaults and overrides

The Zillow property block is built from the scheduled listing and listing
details:

- `id`: `listing.zpid`
- `url`: `listing.detail_url`
- `thumbnail`: `listing.img_src`
- `price`: `listing.unformatted_price` if present, otherwise `listing.price`
- `address`: `listing.address`
- `bedrooms`: `listing.beds`
- `bathrooms`: `listing.baths`
- `area`: `listing.area`
- `original_photos`: from scheduled listing details, if present
- `lot_size_sqft`: from scheduled listing details, if present

The opex block is split into:

- `cleaning`: cleaning fee and annual turn count from opex-by-bedrooms
- `ranged`: currently pool/hot tub low/high from opex-by-bedrooms
- `absolute`: remaining opex fields from bedroom and size tables, excluding
  metadata, cleaning fields, ranged fields, and config-only fields

The config starts with `UW_CONFIG_DEFAULTS`. It may be overridden with:

- FRED rate as `config.fred.value` and `config.fred.date`
- `land_assumptions` from opex config value `land_value`
- `annual_re_appreciation_pct` from opex config value `appreciation`

Construction amenities are returned as the seeded truth-table amenities plus a
synthetic "Furnishings" option. The furnishing low/high values come from the
opex-by-bedrooms row when available.

## Step 7: Build the save payload

`PrepareAndSaveUnderwritingJob.run()` passes the prepared data into:

```python
UnderwritingPayloadBuilder.build(prepared)
```

The builder does not fetch data or persist anything. It maps prepared data into
a `SaveUnderwritingPayload`.

The automated payload sets:

- `zpid`
- `market_id`
- `deal_status = TEMPLATE_GENERATED`
- `is_automated = True`
- `listing_url`
- `property_address`
- `details`
- `taxes`, only when a purchase price exists
- `operating_expenses`

Purchase price is normalized from `prepared.zillow_property.price`.

`details.purchase_details` is created when purchase price exists and includes:

- purchase price
- down payment percentage
- interest rate
- mortgage years
- closing costs percentage

Those financing values come from prepared config, with defaults in
`BaseUnderwritingPayloadBuilder`.

`details.cleaning_cost` is created when cleaning fee and/or turn count is
available. If both are available, annual cleaning cost is calculated as:

```text
cost_per_clean * turns_per_year
```

`taxes` is seeded from config defaults when purchase price exists.

`operating_expenses` are built from:

- cleaning, when both fee and turns are available
- pool/hot tub maintenance low value, when available
- absolute opex values, excluding `consolidated_shipping`

## Step 8: Skip if no purchase price exists

Before saving, `PrepareAndSaveUnderwritingJob.run()` checks for a purchase price.

It first reads:

```python
payload.purchase_price
```

Then, if present, it prefers:

```python
payload.details.purchase_details.purchase_price
```

If the final purchase price is `None`, the job does not call
`SaveUnderwritingService.save()`. It returns:

```json
{
  "zpid": "123",
  "status": "skipped_no_purchase_price"
}
```

This protects the save/calculation path because taxes and purchase-related
financial metrics require a purchase price.

## Step 9: Save and calculate the underwriting

If the payload has a purchase price, the job calls:

```python
SaveUnderwritingService.save(payload)
```

The save service converts the Pydantic payload into:

- parent underwriting data
- detail data
- tax data
- optimization items
- operating expenses
- comp set

### Parent underwriting data

The parent data excludes child fields:

- `details`
- `taxes`
- `optimization_list`
- `operating_expenses`
- `comp_set`

Then `_apply_listing_boolean_fields()` may add:

```python
property_pending = listing.home_status not in (None, "FOR_SALE")
```

To do that, it calls:

```python
ScheduledListingsService.get_by_zpid(payload.zpid)
```

### Tax data

`_build_tax_data()` calculates tax values when `payload.taxes` exists. It gets
purchase price from `payload.details.purchase_details.purchase_price` or
`payload.purchase_price`, then calls:

```python
UnderwritingCalculator.calculate_taxes(...)
```

If taxes exist but purchase price is missing, it raises. In the automated batch
flow, the earlier no-purchase-price guard should prevent that condition.

### Bedroom resolution

`_resolve_bedrooms_for_save()` determines the bedroom count for Airbnb revenue
lookup.

For automated payloads, `details.zillow_property` is not persisted on the
payload. The service falls back to:

```python
ScheduledListingsService.get_by_zpid(payload.zpid)
```

and uses `listing.beds`.

### Detail data and calculated detail fields

`_build_detail_data()` starts from `payload.details`, removes empty values, and
calculates:

- `purchase_details` via `UnderwritingCalculator.calculate_purchase_details(...)`
- `forecasted_revenue`, when possible
- `y1_coc_incl_tax_savings`, when forecasted revenue, tax data, and purchase
  details are all available

If the payload does not already include forecasted revenue, the service tries to
build it with `_build_forecasted_revenue_input(market_id, bedrooms)`.

That method requires:

- configured `MarketService`
- configured `CleanedDataService`
- non-null `market_id`
- non-null `bedrooms`
- `market.market_name_current`
- Airbnb revenue percentiles for `(market_name_current, bedrooms)`

The call chain is:

```text
MarketService.get_by_id(market_id)
  -> MarketRepository.get_by_id(market_id)

CleanedDataService.get_revenue_potential_percentiles(
    key_market=market.market_name_current,
    bedrooms=bedrooms,
)
  -> CleanedDataRepository.get_revenue_potential_percentiles(...)
```

If any required input is missing, forecasted revenue is left unpopulated and the
underwriting still saves. The analyst can fill the missing values later.

Automated underwritings do not persist `details.zillow_property` during save.
That property data is hydrated from scheduled Zillow tables when underwritings
are read.

### Parent calculated fields

After detail data is built, `_apply_calculated_underwriting_fields()` copies and
calculates fields onto the parent underwriting row.

When purchase details exist:

- `purchase_price`

When forecasted revenue exists:

- `low_gross_revenue`
- `mid_gross_revenue`
- `high_gross_revenue`

When both purchase details and forecasted revenue exist:

- `total_oop`
- `prr`
- `budget_to_pp`
- `l_cash_on_cash`
- `m_cash_on_cash`
- `h_cash_on_cash`

These are calculated through `UnderwritingCalculator`.

## Step 10: Persist database records

The save service calls:

```python
UnderwritingRepository.create(
    underwriting_data=...,
    detail_data=...,
    tax_data=...,
    optimization_items=...,
    operating_expenses=...,
    comp_set=...,
)
```

The repository:

1. Adds the parent `Underwriting` row and flushes to get its ID.
2. Adds `UnderwritingDetail` if detail data exists.
3. Adds `UnderwritingTax` if tax data exists.
4. Adds each `UnderwritingOptimizationItem`.
5. Adds each `UnderwritingOperatingExpense`.
6. Adds each `UnderwritingCompSet`.
7. Commits the transaction.
8. Refreshes and returns the parent underwriting.

If anything fails during create, the repository rolls back and re-raises. In
batch mode, the batch job catches that exception for the current `zpid` and
continues to the next listing.

After save succeeds, the single-property job returns:

```json
{
  "zpid": "123",
  "status": "saved",
  "underwriting_id": 456
}
```

## Final batch output

After all selected listings are processed, `BatchPrepareAndSaveUnderwritingsJob`
returns:

```json
{
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
| `found` | Number of scheduled listings selected by `get_active_since()` |
| `processed` | Number of per-listing results produced |
| `saved` | Count of successful new underwriting rows |
| `skipped_existing` | Count skipped because `UnderwritingRepository.get_by_zpid()` found an existing underwriting |
| `skipped_no_purchase_price` | Count skipped because the prepared payload had no usable purchase price |
| `failed` | Count that raised an exception during single-property processing |
| `results` | Ordered per-`zpid` result list matching processing order |

## Status values

The per-listing `status` can be:

| Status | Produced by | Meaning |
|---|---|---|
| `saved` | `PrepareAndSaveUnderwritingJob.run()` | A new draft underwriting was created |
| `skipped_existing` | `PrepareAndSaveUnderwritingJob.run()` | An underwriting already exists for that `zpid` |
| `skipped_no_purchase_price` | `PrepareAndSaveUnderwritingJob.run()` | The listing did not provide a usable purchase price |
| `failed` | `BatchPrepareAndSaveUnderwritingsJob.run()` | An exception occurred for that `zpid`; the batch continued |

## Code map

| Responsibility | File |
|---|---|
| CLI entry point | `scripts/run_uw_auto_prepare.py` |
| Batch selector and result aggregation | `app/workflows/batch_prepare_and_save_underwritings_job.py` |
| By-market batch selector | `app/workflows/batch_prepare_and_save_underwritings_by_market_job.py` |
| Single-property prepare/save orchestration | `app/workflows/prepare_and_save_underwriting_job.py` |
| Cross-domain UW data preparation | `app/workflows/prepare_uw_data_job.py` |
| Pure UW data shaping | `app/iron_bank/services/prepare_uw_data_service.py` |
| Prepared-data to save-payload mapping | `app/iron_bank/services/underwriting_payload_builder.py` |
| Shared payload defaults | `app/iron_bank/services/base_underwriting_payload_builder.py` |
| Save-time calculations and enrichment | `app/iron_bank/services/save_underwriting_service.py` |
| Underwriting persistence | `app/iron_bank/repositories/underwriting_repository.py` |
| Scheduled listing selection | `app/zillow/repositories/scheduled_listings_repository.py` |

## Notes and caveats

- The batch selection uses scheduled listing `created_at`, not Zillow price
  change dates. Price-change reconciliation is handled by the separate
  `BatchReconcileUnderwritingPricesJob`.
- The batch selector does not currently filter on `passes_preset_filters`.
- FRED lookup failures do not fail preparation. `ExternalApiService` retries and
  returns `None` if it cannot obtain a rate.
- Missing market, opex, construction, or Airbnb percentile data generally leaves
  optional fields empty rather than preventing the underwriting from being saved.
- Missing purchase price is the main expected data condition that stops a new
  underwriting from being saved.
