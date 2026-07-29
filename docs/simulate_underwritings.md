# Underwriting simulation (`GET /iron-bank/underwritings` overrides)

The acquisition team can view the underwritings list "as if" it had been
underwritten with different financing assumptions. Two optional query params on
the existing list endpoint activate simulation mode:

| Param | Type | Bounds | Example |
|---|---|---|---|
| `interest_rate` | fractional decimal | `0 <= x < 1` | `0.069` |
| `down_payment_pct` | fractional decimal | `0 <= x <= 1` | `0.1` |

Either or both may be sent. When at least one is present, every underwriting's
financing-derived metrics are recalculated with the override(s) and the list's
**filtering, sorting, and pagination run on the simulated values**. Nothing is
persisted — the service
([`SimulateUnderwritingsService`](../app/iron_bank/services/simulate_underwritings_service.py))
is strictly read-only. Without the params, the endpoint behaves exactly as
before (same service, same response shape, no `simulated`/`simulation` keys).

## What is recalculated

The formulas are the same ones the save/update paths use —
[`UnderwritingCalculator`](../app/iron_bank/services/underwriting_calculator.py)
is the single source of truth.

| Override | Directly changes | Cascades into |
|---|---|---|
| `down_payment_pct` | `down_payment_amount`, `loan_amount` | `total_oop`, `budget_to_pp`, plus everything financing-derived |
| `interest_rate` | `debt_service_annual` (PMT), `principal_pay_down` | per-scenario returns |

Both cascade into per-scenario `annual_free_cash_flow`,
`annual_total_re_return_pct`, top-level `l/m/h_cash_on_cash`, and
`y1_coc_incl_tax_savings` (= (NOI − debt service + tax_savings) / total_oop).
The full input-by-input dependency graph (for every FE-supplied field, not
just the two simulated ones) lives in
[`underwriting_field_dependencies.md`](underwriting_field_dependencies.md).

**Unchanged:** `purchase_price`, `closing_costs_amount`, gross revenues, `prr`,
`operating_expenses_annual`, `co_hosting_fee`, `net_operating_income`, all tax
values, comp_set, zillow hydration, reference labels.

The overlay is **deep**: the top-level metrics and the
`details.purchase_details` / `details.forecasted_revenue` /
`details.y1_coc_incl_tax_savings` JSON they were derived from move together,
so a simulated response is always internally consistent.

Unlike the update path (which calculates from payload-local collections — see
[`update_underwriting_service.md`](update_underwriting_service.md) §10),
simulation always uses the **stored** optimization items and operating
expenses as calculation inputs.

## Filter and sort semantics

`sort_by`, `sort_order`, and all `min/max` filters keep their usual meaning —
but the values they operate on differ by mode:

| Param | Non-simulation | Simulation |
|---|---|---|
| `zpid`, `market_id`, `deal_status`, `analyst_id`, `min/max_purchase_price` | SQL | SQL (simulation never changes these) |
| `min/max_total_oop`, `min/max_l_cash_on_cash` | SQL, stored values | Python, **simulated** values |
| `sort_by=total_oop` / `l_cash_on_cash` | SQL, stored values | Python, **simulated** values |
| `sort_by=id` / `purchase_price` | SQL | Python, same values |
| `total` / `pages` | SQL count | counted after Python filtering |

Filtering the affected bounds in SQL would compare stored values and wrongly
include/exclude rows (a row with stored CoC 8% might simulate to 12% and should
pass `min_l_cash_on_cash=0.10`). Sorting mirrors the SQL path's semantics —
Postgres null placement (nulls first on DESC, last on ASC) and the `id DESC`
tiebreaker — so toggling simulation never reshuffles rows it didn't affect.

## Architecture: two-phase fetch

The PMT / amortization formulas are non-linear in the interest rate, so stored
values can't be scaled — every candidate row must be recalculated **before**
the set can be sorted or paginated:

1. **Lean full-set query**
   ([`UnderwritingRepository.get_simulation_inputs`](../app/iron_bank/repositories/underwriting_repository.py)):
   applies the SQL-safe filters and returns thin rows — stored fallback
   values, the `purchase_details`/`forecasted_revenue` JSON, `tax_savings`,
   and the `optimization_total`/`operating_expense_total` column-property sums
   (all the calculator ever does with the collections is sum them, so one
   synthetic item per total is equivalent to the full child row sets). No
   child selectinloads, no pagination.
2. **Python pass:** recalculate each row, apply the affected filters, compute
   `total`/`pages`, sort, slice the page.
3. **Page hydration** (`get_by_ids`): only the page's rows are fully loaded
   and enriched exactly like the normal list (automated-zillow hydration,
   reference labels), then the simulated values are overlaid.

At ~300 rows the full-set pass is trivial; the per-row payload is small enough
that this scales to tens of thousands of rows before a narrowing filter (e.g.
required `market_id`) would be worth considering.

## Non-simulatable rows: include-and-flag

A row that lacks the inputs to recalculate — no stored `purchase_details` or
`forecasted_revenue`, malformed stored JSON, or a simulated `total_oop` of 0
(e.g. `down_payment_pct=0` with no closing costs or optimization items) — is
**not** dropped and does **not** fail the request. It is returned with its
stored values, flagged `simulated: false`, and filtered/sorted by those stored
values.

## Response contract

- Each row carries `simulated: true|false`. The key is absent outside
  simulation mode (a wrap serializer drops it when `None`).
- The list carries an echo block, absent outside simulation mode:

```json
"simulation": {"interest_rate": 0.069, "down_payment_pct": null}
```

## Known deltas vs stored values

Simulating with a row's **own stored** rate/pct can still differ slightly from
the stored metrics:

- **Rounding drift:** recalculating from stored inputs re-applies the
  calculator's quantization (money `0.01`, percentages `0.0001`, Y1 CoC
  `0.001`), so values can drift by ± one quantum.
- **`y1_coc_incl_tax_savings` freshness:** the stored value is only refreshed
  when a single update produces purchase details, forecasted revenue, *and*
  taxes together, so it can be stale relative to the stored tax row (see
  [`update_underwriting_service.md`](update_underwriting_service.md) §9).
  Simulation always recomputes it from the stored `tax_savings`, i.e. it shows
  the *fresh* value even when the stored one is stale.

## Source map

| Concern | Source |
|---|---|
| Query params, echo block, `simulated` flag | [`app/iron_bank/schemas/get_underwriting.py`](../app/iron_bank/schemas/get_underwriting.py) |
| Controller branching | [`app/iron_bank/controllers/get_underwriting_controller.py`](../app/iron_bank/controllers/get_underwriting_controller.py) |
| Simulation orchestration | [`app/iron_bank/services/simulate_underwritings_service.py`](../app/iron_bank/services/simulate_underwritings_service.py) |
| Lean input query + page hydration | [`app/iron_bank/repositories/underwriting_repository.py`](../app/iron_bank/repositories/underwriting_repository.py) |
| Formulas | [`app/iron_bank/services/underwriting_calculator.py`](../app/iron_bank/services/underwriting_calculator.py) |
| Behavioral coverage | [`tests/iron_bank/test_simulate_underwritings_service.py`](../tests/iron_bank/test_simulate_underwritings_service.py) |
