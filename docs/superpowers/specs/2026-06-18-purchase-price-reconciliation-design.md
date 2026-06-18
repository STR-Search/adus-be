# Purchase Price Reconciliation Design

## Goal

Extend the daily underwriting automation so existing underwritings are
recalculated when their Zillow purchase price changes, without replacing
analyst-owned data or existing assumption collections.

## Daily Workflow

The batch path in `scripts/run_uw_auto_prepare.py` will execute two phases in
the same database session:

1. Run the existing `BatchPrepareAndSaveUnderwritingsJob` for newly created
   Zillow listings.
2. Run a new `BatchReconcileUnderwritingPricesJob` for existing underwritings
   associated with recent Zillow price changes.

The script will return separate `creation` and `price_reconciliation` summaries.
The existing single-`zpid` mode will retain its current prepare-and-save
behavior.

## Candidate Selection

The batch reconciliation job will select `zpid` values from
`zillow.scheduled_listing_details` using `price_change_date`. Because this is a
date-only column, the query will use an overlapping calendar-date window for a
24-hour daily run. Repeated selection is safe because the single reconciliation
job compares normalized prices before updating.

The current system assumes one underwriting per `zpid`.

## Single-Underwriting Reconciliation

`ReconcileUnderwritingPriceJob` will:

1. Load the scheduled listing and existing underwriting, including details,
   taxes, optimization items, operating expenses, and comp set.
2. Normalize the current Zillow price using the same money conversion rules as
   automated underwriting creation.
3. Return a skip result when no underwriting exists, Zillow has no usable
   purchase price, or the normalized Zillow price equals the underwriting
   purchase price.
4. Build a reconciliation payload from the new Zillow price and the existing
   underwriting assumptions.
5. Ask `UpdateUnderwritingService` to recalculate and selectively persist the
   changed financial data.

Failures will be isolated per `zpid` by the batch job.

## Reconciliation Payload Builder

A dedicated `PurchasePriceReconciliationPayloadBuilder` will combine:

- The new normalized Zillow purchase price.
- Existing financing assumptions such as down-payment percentage, interest
  rate, mortgage term, and closing-cost percentage.
- Existing tax percentages.
- Existing forecasted revenue assumptions.
- Existing operating expenses.
- Existing optimization items.

The builder will not call `PrepareUwDataJob`. A purchase-price reconciliation
must not silently refresh mortgage rates, market opex, construction data, or
other assumptions unrelated to the detected Zillow price change.

## Calculation and Persistence Rules

Existing operating expenses and optimization items will be passed to the
calculator as inputs so price-dependent results remain accurate. They will not
be passed to the repository as replacement collections.

The reconciliation update will persist:

- The new top-level `purchase_price`.
- Recalculated purchase details, including loan, down-payment, and closing-cost
  amounts.
- Recalculated tax amounts derived from the new purchase price.
- Recalculated forecasted-return values.
- Recalculated total OOP, PRR, budget-to-purchase-price, and cash-on-cash
  metrics.

This list is exhaustive. The reconciliation update will preserve every other
underwriting field and child record, including:

- Underwriting ID and deal status.
- Analyst notes, links, classifications, and free-form fields.
- Optimization item rows and IDs.
- Operating-expense rows and IDs.
- Comp-set rows and IDs.
- Existing percentage/rate assumptions used as calculation inputs.

Repository calls will use `None` for `optimization_items`,
`operating_expenses`, and `comp_set`. In the existing repository contract,
`None` means leave the collection untouched, while an empty list means delete
all rows.

## Batch Results

The reconciliation summary will include:

- `found`
- `updated`
- `skipped_same_price`
- `skipped_no_underwriting`
- `skipped_no_purchase_price`
- `failed`
- Per-listing results

## Testing

Tests will cover:

- Candidate selection by `price_change_date`.
- Zillow price normalization.
- Every reconciliation skip status.
- A changed price triggering recalculation and update.
- Recalculation using existing opex and optimization items.
- Preservation of opex, optimization, comp-set, and analyst-owned fields.
- Per-listing batch failure isolation and summary counts.
- Combined creation and reconciliation output from the CLI batch path.
