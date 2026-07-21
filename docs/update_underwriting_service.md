# `UpdateUnderwritingService` behavior and recalculation reference

This document describes the complete behavior of
[`UpdateUnderwritingService`](../app/iron_bank/services/update_underwriting_service.py):
what each update path writes, which inputs trigger calculations, how child
records are persisted, and where derived values can become stale.

The service inherits most calculation orchestration from
[`SaveUnderwritingService`](../app/iron_bank/services/save_underwriting_service.py).
The formulas themselves live in
[`UnderwritingCalculator`](../app/iron_bank/services/underwriting_calculator.py),
and persistence behavior lives in
[`UnderwritingRepository`](../app/iron_bank/repositories/underwriting_repository.py).

> **Most important rule:** the normal update path calculates from the current
> request payload. It does not merge the request with all existing database
> values before calculating. A database value may therefore be preserved while
> being treated as absent—or as an empty list—during a calculation in the same
> request.

## Service entry points

The service exposes three independent write paths.

| Method | Purpose | Existing row read before calculation? |
|---|---|---|
| `update(id, UpdateUnderwritingPayload)` | General partial update, child upsert/replacement, and optional recalculation | Only when automatic revenue estimation needs the existing market or bedroom context. The repository also reads before writing. |
| `update_deal_status(...)` | Status change with actor-based analyst and approver assignment | Yes |
| `reconcile_purchase_price(id, SaveUnderwritingPayload)` | Recalculate only price-dependent data after an external listing price changes | The calling workflow builds a payload from the existing row before invoking the method. |

## 1. General update flow

`update()` performs these operations in order:

1. Serializes only explicitly supplied fields with
   `payload.model_dump(exclude_unset=True)`.
2. Splits fields into:
   - top-level `underwritings` fields; and
   - child fields: `details`, `taxes`, `optimization_list`,
     `operating_expenses`, and `comp_set`.
3. Builds calculated tax data only when the `taxes` key was explicitly sent.
4. Builds detail data only when the `details` key was explicitly sent.
5. Copies calculated detail outputs into denormalized top-level underwriting
   columns when the required calculated objects exist.
6. Calls the repository once to update/upsert/replace the affected data.
7. Returns the underwriting ID.

```text
request payload
  -> explicit-field extraction
  -> top-level/child split
  -> optional tax calculation
  -> optional detail and revenue calculations
  -> optional denormalized summary calculations
  -> transactional repository update
```

If the underwriting does not exist, the service raises `LookupError`.

## 2. Update trigger matrix

“Recalculate” below means calculator logic runs during this request. “Persist
only” means dependent values are not automatically refreshed.

| Changed input | What is updated | Recalculation behavior |
|---|---|---|
| Any top-level scalar, flag, enum, date, link, or text field | Matching `underwritings` column | Persist only, unless a later calculation in the same request overwrites that field |
| Top-level `purchase_price` | `underwritings.purchase_price` | No purchase-detail, tax, revenue, OOP, PRR, budget, or CoC recalculation |
| `details.purchase_details` | Calculated `purchase_details` JSON and top-level `purchase_price` | Recalculates financing amounts; may also trigger automatic forecasted-revenue estimation |
| `details.forecasted_revenue` | Calculated forecasted-revenue scenarios and eligible top-level metrics | Requires `details.purchase_details` in the same request; stored purchase details are not used as fallback |
| `market_id` | `underwritings.market_id` | Does not trigger a calculation by itself |
| `details.zillow_property.bedrooms` | Detail Zillow JSON; may supply bedrooms for a revenue lookup | Used only when `purchase_details` triggers automatic revenue estimation |
| `taxes` | Tax row, including all derived tax values | Requires a purchase price in the current payload |
| `optimization_list` | Fully replaces optimization rows | Influences calculations only when details or taxes trigger them in the same request |
| `operating_expenses` | Fully replaces expense rows | Influences scenario calculations only when forecasted revenue is calculated in the same request |
| `comp_set` | Fully replaces comp rows | Never directly triggers a calculation |
| `deal_status` through the general update | Direct status write | Does not apply actor-based analyst/approver assignment rules |
| `details.analyst_notes`, `cleaning_cost`, or `property_taxes` | Supplied detail columns | No calculation |

## 3. Explicit, omitted, and null fields

The update schema uses Pydantic defaults, but `exclude_unset=True` means an
omitted default is not considered an update.

### Top-level fields

- Omitted key: existing database value is preserved.
- Explicit non-null value: column is updated.
- Explicit `null`: column is set to `NULL`, where validation and the database
  permit it.
- A directly supplied calculated field can be overwritten later in the same
  request if the service recalculates that field.

For example, if both top-level `purchase_price` and
`details.purchase_details.purchase_price` are supplied, the purchase-details
value wins because calculated fields are applied after the initial top-level
payload is extracted.

### Detail fields

- Omitted `details`: the detail row is untouched.
- Supplied `details` object: only the non-null fields produced by
  `_build_detail_data()` are upserted.
- Explicit `details: null`: no detail update or deletion occurs.
- Explicit `null` for an inner detail field is removed by
  `_without_empty_values()` and therefore does **not** clear the stored column.
- If no detail row exists, the repository creates one from the produced detail
  dictionary.

### Taxes

- Omitted `taxes`: the tax row is untouched.
- Explicit `taxes: null`: `_build_tax_data()` returns `None`, so the tax row is
  still untouched; it is not deleted or cleared.
- A non-null tax object is recalculated and then upserted.
- `UnderwritingTaxInput` requires all four assumption inputs, so this is not a
  partial tax-assumption patch.

### Child collections

The three child collections use replacement semantics.

| Payload state | Repository argument | Database result |
|---|---|---|
| Key omitted | `None` | Existing rows are preserved |
| Key sent as `[]` | Empty list | All existing rows are deleted |
| Key sent with items | Serialized item list | All existing rows are deleted and replaced |

This applies independently to:

- `optimization_list`;
- `operating_expenses`; and
- `comp_set`.

## 4. Purchase-detail calculations

When `details.purchase_details` is sent, the service calls
`calculate_purchase_details()`.

```text
down_payment_amount = purchase_price * down_payment_pct
loan_amount = purchase_price - down_payment_amount
closing_costs_amount = purchase_price * closing_costs_pct
```

The resulting JSON contains the original purchase inputs plus these three
calculated values. The service also copies its `purchase_price` into the
top-level underwriting row.

This calculation does not use stored purchase details. All required purchase
inputs must be present in the request's `PurchaseDetailsInput`.

## 5. Forecasted-revenue calculations

A forecasted-revenue calculation requires:

1. calculated `purchase_details` from the current request; and
2. either:
   - explicit `details.forecasted_revenue`; or
   - a successfully auto-built forecasted-revenue input.

If explicit forecasted revenue is sent without purchase details in the same
`details` payload, the service raises:

```text
ValueError: purchase_details is required to calculate forecasted revenue
```

### Inputs used by the calculator

```text
monthly_opex_total = sum(operating_expense.monthly_amount)
optimization_total = sum(optimization_item.total_price)

total_oop = down_payment_amount
          + closing_costs_amount
          + optimization_total

annual_debt_service = monthly_mortgage_payment * 12
year_one_principal_paydown = opening_loan - loan_balance_after_12_months
annual_appreciation = purchase_price * annual_re_appreciation_pct
```

The monthly mortgage payment uses the amortizing-payment formula. A zero
interest rate is handled as `loan_amount / number_of_months`.

### Scenario calculations

The low, mid, and high scenarios use different operating-expense multipliers.

| Scenario | Opex multiplier |
|---|---:|
| Low | `0.96` |
| Mid | `1.00` |
| High | `1.04` |

For each scenario:

```text
annual_opex = monthly_opex_total * 12 * scenario_multiplier
co_hosting_fee = gross_revenue * co_hosting_fee_pct
net_operating_income = gross_revenue - annual_opex - co_hosting_fee
annual_free_cash_flow = net_operating_income - annual_debt_service

annual_total_re_return_pct =
    (annual_free_cash_flow + principal_paydown + annual_appreciation)
    / total_oop
```

Each stored scenario contains:

- the input `forecasted_revenue`;
- `operating_expenses_annual`;
- `co_hosting_fee`;
- `net_operating_income`;
- `debt_service_annual`;
- `annual_free_cash_flow`;
- `principal_pay_down`;
- `annual_re_appreciation`; and
- `annual_total_re_return_pct`.

## 6. Automatic forecasted-revenue estimation

Automatic estimation is attempted only when all of the following are true:

- the request contains `details`;
- `details.purchase_details` is non-null; and
- `details.forecasted_revenue` is null or omitted.

The existing underwriting is fetched only in this case. Unrelated updates do
not incur this extra lookup.

### Market resolution

The market is resolved as:

1. non-null `payload.market_id`; otherwise
2. `existing.market_id`.

### Bedroom resolution

Bedrooms are resolved in this order:

1. `payload.details.zillow_property.bedrooms`;
2. `existing.detail.zillow_property["bedrooms"]`;
3. `listings_service.get_by_zpid(existing.zpid).beds`; or
4. unavailable.

The scheduled-listing lookup is intended for automated underwritings. Stored
Zillow JSON is intended for non-automated underwritings.

### Airbnb percentile lookup

When both market and bedrooms are available:

1. `market_service.get_by_id(market_id)` resolves
   `market_name_current`.
2. `cleaned_data_service.get_revenue_potential_percentiles()` looks up revenue
   percentiles by `(market_name_current, bedrooms)`.
3. The service builds this forecast input:

```text
co_hosting_fee_pct = 0
annual_re_appreciation_pct = 0.0425
low scenario revenue = cleaned-data low percentile
mid scenario revenue = cleaned-data mid percentile
high scenario revenue = cleaned-data high percentile
```

The resulting input then goes through the normal scenario calculator.

### Graceful skip conditions

The estimate is skipped without failing the update if any of these are missing:

- market service;
- cleaned-data service;
- market ID;
- bedrooms;
- market record;
- `market_name_current`; or
- percentile data for the market and bedroom count.

In that case, purchase details can still be updated, but forecasted revenue and
its downstream metrics are not produced.

### Market-clearing edge case

If the caller explicitly sends `market_id: null` while purchase details trigger
automatic estimation, calculation market resolution falls back to the existing
market. The repository will nevertheless clear the top-level `market_id` in the
same update. This can leave newly calculated revenue based on the old market
beside a null stored market ID.

## 7. Top-level derived fields

After detail calculation, `_apply_calculated_underwriting_fields()` copies or
calculates denormalized summary fields.

| Top-level field | Source or formula | Required current-request output |
|---|---|---|
| `purchase_price` | `purchase_details.purchase_price` | Purchase details |
| `low_gross_revenue` | Low scenario input revenue | Forecasted revenue |
| `mid_gross_revenue` | Mid scenario input revenue | Forecasted revenue |
| `high_gross_revenue` | High scenario input revenue | Forecasted revenue |
| `total_oop` | Down payment + closing costs + optimization total | Purchase details and forecasted revenue under the current orchestration gate |
| `prr` | `mid_gross_revenue / purchase_price` | Purchase details and forecasted revenue |
| `budget_to_pp` | `total_oop / purchase_price` | Purchase details and forecasted revenue |
| `l_cash_on_cash` | Low annual free cash flow / total OOP | Purchase details and forecasted revenue |
| `m_cash_on_cash` | Mid annual free cash flow / total OOP | Purchase details and forecasted revenue |
| `h_cash_on_cash` | High annual free cash flow / total OOP | Purchase details and forecasted revenue |

The method has three gates:

1. No `detail_data`: nothing is derived.
2. Purchase details but no forecasted revenue: only top-level purchase price is
   derived.
3. Forecasted revenue but no purchase details: gross-revenue fields can be
   copied, but OOP, PRR, budget ratio, and CoC are skipped. In the normal build
   path, explicit forecasted revenue without purchase details fails earlier.

## 8. Tax calculations

Taxes are calculated only when the `taxes` key contains a non-null object.

The purchase price is selected in this order:

1. `payload.details.purchase_details.purchase_price`; otherwise
2. top-level `payload.purchase_price`.

The existing database purchase price is not used as fallback. If neither value
is present, the service raises:

```text
ValueError: purchase_price is required to calculate underwriting taxes
```

The calculator uses the request's `optimization_list`:

```text
optimization_total = sum(optimization_item.total_price)

improvement_basis =
    purchase_price * (1 - land_assumptions_pct)
    + optimization_total

estimated_short_life_assets = improvement_basis * sla_multiplier_pct
y1_loss_from_depreciation = estimated_short_life_assets * bonus_amount_pct
tax_savings = tax_rate_pct * y1_loss_from_depreciation
```

The tax row stores the four input assumptions and the four derived values.

## 9. Y1 CoC including tax savings

`details.y1_coc_incl_tax_savings` is recalculated only when the current request
produces all three of these:

- forecasted revenue;
- tax data; and
- purchase details.

For each scenario:

```text
y1_coc_incl_tax_savings =
    (net_operating_income - debt_service_annual + tax_savings)
    / total_oop
```

Updating taxes alone refreshes the tax row but does not refresh stored Y1 CoC
including tax savings.

## 10. Payload-local calculation caveats

These are the most important consequences of not merging stored inputs into the
calculation payload.

| Request pattern | What happens | Potential inconsistency |
|---|---|---|
| Change only `optimization_list` | Optimization rows are replaced; no economics or tax calculation runs | Stored OOP, tax values, and returns can become stale |
| Change only `operating_expenses` | Expense rows are replaced; no scenario calculation runs | Stored NOI, free cash flow, and CoC can become stale |
| Change only taxes and include top-level purchase price | Tax row recalculates | Stored Y1 CoC including tax savings remains stale |
| Send purchase details but omit `optimization_list` | Calculations use an empty optimization list; stored optimization rows are preserved | Calculated OOP and returns may disagree with stored optimization rows |
| Send purchase and forecast details but omit `operating_expenses` | Scenario calculations use zero monthly opex; stored expense rows are preserved | Scenario economics may disagree with stored expense rows |
| Send forecasted revenue without purchase details | Request fails with `ValueError` | Stored purchase details are not used |
| Change only `market_id` | Market changes; no revenue lookup runs | Revenue and returns remain unchanged |
| Change only top-level `purchase_price` | Direct scalar write | Detail purchase price and price-dependent metrics remain unchanged |
| Send a top-level calculated field plus calculable details | Calculator runs after initial scalar extraction | Calculator-produced value wins |

The collection defaults are especially important:

- `payload.optimization_list` is an empty list when omitted;
- `payload.operating_expenses` is an empty list when omitted; but
- `exclude_unset=True` prevents those omitted keys from replacing stored rows.

Therefore, a list can be **empty for calculation purposes** while the existing
database collection is **preserved for persistence purposes**.

### Payload guard: purchase details require explicit collections

`UpdateUnderwritingPayload` rejects (HTTP 422) any request that sends
`details.purchase_details` without **explicitly** sending both
`optimization_list` and `operating_expenses`. This closes the worst variant of
the caveats above: recalculating OOP, returns, and scenario economics against
empty default lists while non-empty stored rows are silently preserved.

- Explicit empty lists are accepted — that is a deliberate "there are none"
  (and, per the replacement semantics, clears the stored rows).
- Detail updates without `purchase_details` (e.g. `analyst_notes`) are not
  affected.
- Internal paths built on `SaveUnderwritingPayload` (e.g. purchase-price
  reconciliation) are not affected.

## 11. Deal-status update path

The dedicated route is:

```text
PATCH /underwritings/{underwriting_id}/deal-status
```

It receives the authenticated user's ID as `actor_user_id` and follows these
rules:

| Condition | Fields written |
|---|---|
| Every call | `deal_status = requested status` |
| Existing `analyst_id` is null | `analyst_id = actor_user_id` |
| Existing `analyst_id` is already set | Analyst is preserved |
| Requested status is `PRESENT_TO_CLIENTS` | `approver_id = actor_user_id` |
| Requested status is anything else | Approver is preserved |

The analyst assignment is “first touch only.” The approver assignment is not:
every transition to `PRESENT_TO_CLIENTS` overwrites the approver with the
current actor.

If the underwriting does not exist, the method raises `LookupError`.

> Setting `deal_status` through the general `PUT /underwritings/{id}` path does
> not apply any actor-assignment behavior. That path can also directly set
> `analyst_id` and `approver_id`.

## 12. Purchase-price reconciliation

`reconcile_purchase_price()` is used by
[`ReconcileUnderwritingPriceJob`](../app/workflows/reconcile_underwriting_price_job.py)
when a scheduled listing's price changes.

### Workflow trigger

The job:

1. Gets the latest underwriting for a `zpid`.
2. Gets the scheduled listing.
3. Reads `unformatted_price`, falling back to `price`.
4. Normalizes it to a positive `Decimal`.
5. Skips when:
   - no underwriting exists;
   - no valid listing price exists; or
   - the price equals the current underwriting purchase price.
6. Builds a complete calculation payload from stored underwriting data, with
   the new purchase price substituted.
7. Calls `reconcile_purchase_price()`.

The
[`PurchasePriceReconciliationPayloadBuilder`](../app/iron_bank/services/purchase_price_reconciliation_payload_builder.py)
requires existing:

- purchase details;
- forecasted revenue; and
- taxes.

It raises `ValueError` if any are missing.

### What reconciliation recalculates

Reconciliation rebuilds:

- purchase details and financing-derived amounts;
- forecasted-revenue scenario economics;
- Y1 CoC including tax savings;
- all derived tax values; and
- eligible top-level calculated values.

It filters top-level output through `_PRICE_RECONCILIATION_FIELDS`, so only
these columns are updated:

- `purchase_price`;
- `total_oop`;
- `prr`;
- `budget_to_pp`;
- `l_cash_on_cash`;
- `m_cash_on_cash`; and
- `h_cash_on_cash`.

It deliberately does not update top-level low/mid/high gross revenue because a
price change does not change the gross-revenue inputs.

### What reconciliation preserves

The method passes `None` for:

- `optimization_items`;
- `operating_expenses`; and
- `comp_set`.

Those stored rows are not replaced. The optimization and expense values from
the builder's payload are still used as calculation inputs.

All unrelated top-level columns are also preserved.

## 13. Rounding and validation errors

The calculator rounds:

| Value type | Precision |
|---|---:|
| Scenario money values | `0.01` |
| General percentages | `0.0001` |
| Y1 CoC including tax savings | `0.001` |

Relevant calculation errors include:

| Condition | Error |
|---|---|
| Taxes sent without a purchase price in the payload | `purchase_price is required to calculate underwriting taxes` |
| Forecasted revenue sent without purchase details in the same payload | `purchase_details is required to calculate forecasted revenue` |
| Calculated total OOP is zero | `total_oop is required to calculate forecasted revenue` |
| Cash-on-cash receives zero total OOP | `total_oop is required to calculate cash on cash` |
| Mid gross revenue is zero during PRR | `mid gross revenue is required to calculate PRR` |
| Purchase price is zero during budget calculation | `purchase_price is required to calculate budget to PP` |

The general-update controller maps:

- `ValueError` to HTTP 400;
- `LookupError` to HTTP 404; and
- unexpected errors to HTTP 500 with `Failed to update underwriting`.

Missing data for automatic revenue estimation is not an error. The service
logs the reason and continues without the estimate.

## 14. Repository transaction behavior

The repository update performs the following in one transaction:

1. Loads the underwriting and its child relationships.
2. Assigns supplied top-level fields.
3. Upserts detail fields when `detail_data` is non-null.
4. Upserts taxes when `tax_data` is non-null.
5. Replaces each child collection whose argument is non-null.
6. Commits and refreshes the underwriting.

Any exception rolls back the entire update.

The detail and tax upserts update individual model attributes from their
dictionaries. They do not replace the whole child row. Collection updates, by
contrast, delete all old rows and insert the new set.

## 15. Safe request patterns

### Metadata-only edit

Send only the changed top-level fields. No calculation is attempted and omitted
children remain untouched.

```json
{
  "note": "Updated analyst note",
  "deal_score": 82
}
```

### Full economics recalculation

Send all calculation dependencies together:

- `details.purchase_details`;
- either explicit `details.forecasted_revenue` or enough market/bedroom context
  for automatic estimation;
- the complete current `optimization_list`;
- the complete current `operating_expenses`; and
- `taxes` when tax outputs and Y1 CoC including tax savings must refresh.

This avoids calculating against empty default lists while preserving non-empty
stored rows.

### Clear a collection

Send the collection key with an empty list. Omitting it preserves the current
rows.

```json
{
  "comp_set": []
}
```

### Status transition with ownership semantics

Use the dedicated deal-status endpoint rather than the general PUT so the
authenticated actor is applied according to the analyst and approver rules.

## 16. Source map

| Concern | Source |
|---|---|
| Update orchestration and specialized paths | [`app/iron_bank/services/update_underwriting_service.py`](../app/iron_bank/services/update_underwriting_service.py) |
| Shared detail/tax construction and top-level derivation | [`app/iron_bank/services/save_underwriting_service.py`](../app/iron_bank/services/save_underwriting_service.py) |
| Financial formulas and rounding | [`app/iron_bank/services/underwriting_calculator.py`](../app/iron_bank/services/underwriting_calculator.py) |
| Partial upserts, collection replacement, and transaction | [`app/iron_bank/repositories/underwriting_repository.py`](../app/iron_bank/repositories/underwriting_repository.py) |
| Update payload defaults, omission, and null behavior | [`app/iron_bank/schemas/update_underwriting.py`](../app/iron_bank/schemas/update_underwriting.py) |
| Calculation input schemas | [`app/iron_bank/schemas/save_underwriting.py`](../app/iron_bank/schemas/save_underwriting.py) |
| Price-change trigger | [`app/workflows/reconcile_underwriting_price_job.py`](../app/workflows/reconcile_underwriting_price_job.py) |
| Reconciliation payload assembly | [`app/iron_bank/services/purchase_price_reconciliation_payload_builder.py`](../app/iron_bank/services/purchase_price_reconciliation_payload_builder.py) |
| Behavioral coverage | [`tests/iron_bank/test_update_underwriting_service.py`](../tests/iron_bank/test_update_underwriting_service.py) |

