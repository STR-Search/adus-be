# BatchReconcileUnderwritingPricesJob

This document explains how `BatchReconcileUnderwritingPricesJob` decides which
existing underwritings need purchase-price reconciliation, what service and
repository methods are called, and what output the job returns.

The job is the batch wrapper around the single-property workflow
`ReconcileUnderwritingPriceJob`. It finds Zillow listing details with recent
price changes, runs the single-property reconciliation workflow for each `zpid`,
and returns a summary of updated, skipped, and failed items.

## Entry point

The main entry point is `scripts/run_uw_auto_prepare.py`.

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

This document focuses on the `price_reconciliation` side.

## High-level flow

```text
BatchReconcileUnderwritingPricesJob.run(since_hours, limit)
  -> ScheduledListingDetailsService.get_price_changed_zpids_since(...)
    -> ScheduledListingDetailsRepository.get_price_changed_since(...)
  -> for each zpid:
    -> ReconcileUnderwritingPriceJob.run(zpid)
      -> UnderwritingRepository.get_by_zpid(zpid)
      -> ScheduledListingsService.get_by_zpid(zpid)
      -> PurchasePriceReconciliationPayloadBuilder.normalize_purchase_price(...)
      -> skip if no existing underwriting, no Zillow price, or same price
      -> PurchasePriceReconciliationPayloadBuilder.build(...)
      -> UpdateUnderwritingService.reconcile_purchase_price(...)
        -> UnderwritingRepository.update(...)
  -> return aggregate summary and per-zpid results
```

## Step 1: Build the job dependencies

`BatchReconcileUnderwritingPricesJob.from_session(db)` creates:

- `ScheduledListingDetailsService(ScheduledListingDetailsRepository(db))`
- `ReconcileUnderwritingPriceJob.from_session(db)`

`ReconcileUnderwritingPriceJob.from_session(db)` creates:

- `ScheduledListingsService(ScheduledListingsRepository(db))`
- `UnderwritingRepository(db)`
- `PurchasePriceReconciliationPayloadBuilder()`
- `UpdateUnderwritingService(underwriting_repository)`

Unlike the automated creation flow, the update service is not configured with
market, scheduled-listing, or cleaned Airbnb data services here. Reconciliation
uses the existing underwriting's saved assumptions and only recalculates fields
that depend on purchase price.

## Step 2: Select zpids with recent Zillow price changes

`BatchReconcileUnderwritingPricesJob.run()` receives:

- `since_hours`: required lookback window
- `limit`: optional maximum number of `zpid`s to process

It calls:

```python
ScheduledListingDetailsService.get_price_changed_zpids_since(
    since_hours=since_hours,
    limit=limit,
)
```

That service delegates directly to:

```python
ScheduledListingDetailsRepository.get_price_changed_since(...)
```

The repository query selects `ScheduledListingDetail.zpid` where:

```python
ScheduledListingDetail.price_change_date >= cutoff_date
```

`cutoff_date` is computed as:

```python
(datetime.now(timezone.utc) - timedelta(hours=since_hours)).date()
```

So the selector uses a date-level comparison, not a timestamp comparison.

It orders the rows by:

1. `price_change_date desc`
2. `zpid`

If `limit` is provided, the query applies that limit.

Important: this selector starts from `zillow.scheduled_listing_details`, not
`zillow.scheduled_listings`. It does not check `keep_updated`, `remove_listing`,
or `passes_preset_filters`. The rule is simply "listing details whose
`price_change_date` is on or after the cutoff date."

## Step 3: Process each selected zpid

For every `zpid` returned by `get_price_changed_zpids_since()`, the batch job
calls:

```python
ReconcileUnderwritingPriceJob.run(zpid)
```

The batch job catches exceptions per `zpid`. A failure for one property becomes
a per-item result with `status: "failed"` and does not stop the rest of the
batch.

## Step 4: Skip if no underwriting exists

The single-property job starts with:

```python
UnderwritingRepository.get_by_zpid(zpid)
```

`get_by_zpid()` queries `iron_bank.underwritings` by `zpid`, eager-loads child
records, orders by newest underwriting ID first, and returns the latest match.

If it does not find a row, the job stops and returns:

```json
{
  "zpid": "123",
  "status": "skipped_no_underwriting"
}
```

This matters because reconciliation does not create underwritings. It only
updates existing rows.

## Step 5: Read the current Zillow listing price

If an underwriting exists, the job loads the scheduled Zillow listing:

```python
ScheduledListingsService.get_by_zpid(zpid)
  -> ScheduledListingsRepository.get_by_zpid(zpid)
```

Then it chooses the raw Zillow price:

```python
raw_price = None if listing is None else listing.unformatted_price or listing.price
```

So `unformatted_price` is preferred when present. If there is no scheduled
listing row, or both Zillow price fields are empty, the raw price is `None`.

## Step 6: Normalize and validate the Zillow purchase price

The job calls:

```python
PurchasePriceReconciliationPayloadBuilder.normalize_purchase_price(raw_price)
```

The normalizer accepts:

- positive `Decimal` values
- positive `int` and `float` values
- strings that can be cleaned into positive decimals, such as `"$525,000"`

It returns `None` for:

- `None`
- zero or negative values
- strings with no numeric content
- strings that cannot be parsed as a decimal

If the normalized Zillow purchase price is `None`, the job stops and returns:

```json
{
  "zpid": "123",
  "status": "skipped_no_purchase_price",
  "underwriting_id": 456
}
```

## Step 7: Skip if the price did not change

If the normalized Zillow purchase price matches the stored parent underwriting
price:

```python
underwriting.purchase_price == purchase_price
```

the job stops and returns:

```json
{
  "zpid": "123",
  "status": "skipped_same_price",
  "underwriting_id": 456
}
```

Only different prices proceed to recalculation.

## Step 8: Build a reconciliation payload from existing assumptions

When the Zillow purchase price differs from `underwriting.purchase_price`, the
job calls:

```python
PurchasePriceReconciliationPayloadBuilder.build(
    underwriting=underwriting,
    purchase_price=purchase_price,
)
```

The builder creates a `SaveUnderwritingPayload` that contains only the data
needed to recalculate purchase-price-dependent fields. It does not fetch data or
persist anything.

The builder requires the existing underwriting to have:

- `underwriting.detail`
- `underwriting.detail.purchase_details`
- `underwriting.detail.forecasted_revenue`
- `underwriting.taxes`

If any of those are missing, the builder raises `ValueError`. In batch mode,
that exception is caught by the batch wrapper and returned as a per-item
`failed` result.

The payload preserves these existing assumptions:

- `is_automated`
- down payment percentage
- interest rate
- mortgage years
- closing costs percentage
- forecasted revenue low/mid/high gross revenue values
- co-hosting fee percentage
- annual real-estate appreciation percentage
- tax assumptions
- optimization items
- operating expenses

The payload replaces only:

- `details.purchase_details.purchase_price`

with the newly normalized Zillow purchase price.

## Step 9: Recalculate purchase-price-dependent fields

The job calls:

```python
UpdateUnderwritingService.reconcile_purchase_price(
    underwriting.id,
    payload,
)
```

This method uses the same calculation helpers as the save/update flow, but it
intentionally writes back only the fields that should change when purchase price
changes.

First it builds tax data:

```python
_build_tax_data(payload)
  -> UnderwritingCalculator.calculate_taxes(...)
```

Then it builds detail data:

```python
_build_detail_data(payload, tax_data, market_id=payload.market_id, bedrooms=bedrooms)
```

For this reconciliation payload, forecasted revenue is already present, so
`_build_detail_data()` recalculates forecasted-revenue scenario metrics using:

- the new purchase details
- existing forecasted revenue assumptions
- existing operating expenses
- existing optimization items

It also recalculates `y1_coc_incl_tax_savings` when forecasted revenue, tax
data, and purchase details are available.

Then `_apply_calculated_underwriting_fields()` calculates parent-level values
into a temporary dictionary.

`reconcile_purchase_price()` filters that dictionary down to:

- `purchase_price`
- `total_oop`
- `prr`
- `budget_to_pp`
- `l_cash_on_cash`
- `m_cash_on_cash`
- `h_cash_on_cash`

The method deliberately does not update all possible parent fields. For example,
low/mid/high gross revenue values are not included in the reconciliation write
set because the gross revenue assumptions themselves are carried over from the
existing underwriting.

## Step 10: Persist the update

The update service calls:

```python
UnderwritingRepository.update(
    underwriting_id=underwriting_id,
    underwriting_data=underwriting_data,
    detail_data=jsonable_encoder(detail_data),
    tax_data=tax_data,
    optimization_items=None,
    operating_expenses=None,
    comp_set=None,
)
```

The repository:

1. Loads the existing underwriting by ID.
2. Updates the filtered parent underwriting fields.
3. Upserts detail data.
4. Upserts tax data.
5. Leaves optimization items unchanged.
6. Leaves operating expenses unchanged.
7. Leaves comp set unchanged.
8. Commits the transaction.
9. Refreshes and returns the parent underwriting.

If the underwriting ID cannot be found, the service raises:

```text
LookupError("Underwriting {underwriting_id} not found")
```

In batch mode, that exception is caught and returned as a per-item `failed`
result.

After reconciliation succeeds, the single-property job returns:

```json
{
  "zpid": "123",
  "status": "updated",
  "underwriting_id": 456
}
```

## Final batch output

After all selected `zpid`s are processed,
`BatchReconcileUnderwritingPricesJob` returns:

```json
{
  "found": 4,
  "processed": 4,
  "updated": 1,
  "skipped_same_price": 1,
  "skipped_no_underwriting": 1,
  "skipped_no_purchase_price": 0,
  "failed": 1,
  "results": [
    {
      "zpid": "1",
      "status": "updated",
      "underwriting_id": 10
    },
    {
      "zpid": "2",
      "status": "skipped_same_price",
      "underwriting_id": 20
    },
    {
      "zpid": "3",
      "status": "skipped_no_underwriting"
    },
    {
      "zpid": "4",
      "status": "failed",
      "error": "boom"
    }
  ]
}
```

Field meanings:

| Field | Meaning |
|---|---|
| `found` | Number of `zpid`s selected by `get_price_changed_zpids_since()` |
| `processed` | Number of per-`zpid` results produced |
| `updated` | Count of underwritings updated with a changed Zillow purchase price |
| `skipped_same_price` | Count skipped because Zillow price equals stored `underwriting.purchase_price` |
| `skipped_no_underwriting` | Count skipped because no underwriting exists for the `zpid` |
| `skipped_no_purchase_price` | Count skipped because the Zillow listing price could not be normalized |
| `failed` | Count that raised an exception during single-property processing |
| `results` | Ordered per-`zpid` result list matching processing order |

## Status values

The per-`zpid` `status` can be:

| Status | Produced by | Meaning |
|---|---|---|
| `updated` | `ReconcileUnderwritingPriceJob.run()` | Existing underwriting was recalculated and updated |
| `skipped_same_price` | `ReconcileUnderwritingPriceJob.run()` | Zillow price matched stored underwriting purchase price |
| `skipped_no_underwriting` | `ReconcileUnderwritingPriceJob.run()` | No underwriting exists for that `zpid` |
| `skipped_no_purchase_price` | `ReconcileUnderwritingPriceJob.run()` | Zillow listing had no usable purchase price |
| `failed` | `BatchReconcileUnderwritingPricesJob.run()` | An exception occurred for that `zpid`; the batch continued |

## Code map

| Responsibility | File |
|---|---|
| CLI entry point | `scripts/run_uw_auto_prepare.py` |
| Batch selector and result aggregation | `app/workflows/batch_reconcile_underwriting_prices_job.py` |
| Single-property reconciliation orchestration | `app/workflows/reconcile_underwriting_price_job.py` |
| Price normalization and reconciliation payload | `app/iron_bank/services/purchase_price_reconciliation_payload_builder.py` |
| Reconciliation update/calculation | `app/iron_bank/services/update_underwriting_service.py` |
| Shared save/update calculations | `app/iron_bank/services/save_underwriting_service.py` |
| Core underwriting math | `app/iron_bank/services/underwriting_calculator.py` |
| Underwriting persistence | `app/iron_bank/repositories/underwriting_repository.py` |
| Price-change zpid selection | `app/zillow/repositories/scheduled_listing_details_repository.py` |
| Current Zillow price lookup | `app/zillow/repositories/scheduled_listings_repository.py` |

## Notes and caveats

- The batch selection uses `ScheduledListingDetail.price_change_date`, not
  `ScheduledListing.created_at`.
- The selector compares dates, not exact timestamps. A `since_hours` cutoff is
  converted to a UTC date before querying.
- The selector does not check whether the listing is active, removed, or passed
  preset filters.
- Reconciliation does not create underwritings. Missing underwritings are
  skipped.
- Reconciliation requires existing purchase details, forecasted revenue, and
  tax assumptions. Missing required existing data becomes a failed item in the
  batch result.
- The update preserves optimization items, operating expenses, comp set, and
  forecasted gross revenue assumptions. It updates purchase-price-dependent
  detail, tax, and parent summary fields.
