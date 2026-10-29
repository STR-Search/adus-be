# Analytics API Design — "Ready now" metrics

## Goal

Serve the dashboard metrics that the Analytics Dashboard Proposal (2026-10-20)
marks **Ready now**, using the analytics architecture introduced in commit
`9745a59` ("implement analytics module with deal and home status breakdowns").
This document decides where every query lives, what each endpoint accepts and
returns, and how every list in every response is ordered.

## Scope

In scope — the "Ready now" metrics:

| Group | Metrics |
|---|---|
| A. New listings | 1, 2, 3, 4 |
| B. Pipeline today | 5, 7 |
| C. Off the market | 10, 11, 12 |
| D. Conversion | 15 |
| E. Markets and deal quality | 18, 19, 20, 21, 22, 23, 24 |
| F. Duplicates and data quality | 25, 26 |

Out of scope:

- **Metric 6 (deals per stage).** Underwritings are described by their deal
  status only; there is no stage grouping (D4). Metric 5 already shows every
  status.
- Metrics with caveats (8, 13, 14, 27). They wait for the general process log
  schema, which is designed separately.
- Client metrics (16, 17). No client data source yet.
- Metric 9. It is missing from the proposal's tables; resolve with the
  proposal owner before it is designed.
- The headline `summary` endpoint, caching, and route-level access control.

## What already exists (commit `9745a59`)

```text
GET /analytics/underwritings/deal-status-breakdown
  -> AnalyticsController.get_deal_status_breakdown
    -> UnderwritingAnalyticsService       (app/iron_bank/services/analytics/)
      -> UnderwritingAnalyticsRepository  (app/iron_bank/repositories/)

GET /analytics/listings/home-status-breakdown
  -> AnalyticsController.get_home_status_breakdown
    -> ListingAnalyticsService            (app/zillow/services/)
      -> ListingAnalyticsRepository       (app/zillow/repositories/)
```

The commit also fixes the layering rule in `CLAUDE.md`:

- `app/analytics/` is a **read-only composition layer**. It owns no tables,
  models or migrations.
- Each domain owns its own analytics queries (an analytics repository and an
  analytics service inside that domain) and its own response schemas.
- `app/analytics/` holds only the controller, router, *composed* response
  schemas, and — solely for metrics that need a SQL join across domain
  schemas — its own read-only repositories.

No frontend consumes these endpoints yet, so their response shapes can still
change without a migration path. This design uses that window.

## Decisions

### D1. Market means `underwritings.market_id` (decided)

Every metric that filters or groups by market uses
`iron_bank.underwritings.market_id`.

Consequences:

- **Underwriting metrics** filter on `Underwriting.market_id` directly. This is
  what `deal-status-breakdown` already does.
- **Cross-domain metrics** (listing joined to underwriting) also filter on the
  underwriting's `market_id`, never the preset's.
- **Listing-only metrics** (1, the listing half of 26, and the listing
  denominator of 2) have no underwriting to read a market from. A listing that
  was never underwritten has no market under this definition. These metrics
  filter and group by **preset** (`preset_id`) instead, and do not accept
  `market_id`.
- The existing `home-status-breakdown` currently filters `market_id` through
  `scheduled_presets.market_id`. That is a second meaning of "market" and is
  removed: the endpoint switches to `preset_id` (see
  [Changes to existing endpoints](#changes-to-existing-endpoints)).

### D2. Legacy sheet rows are excluded by default (proposed)

`Underwriting.source` already records provenance (`UnderwritingSource`:
`adus`, `legacy_sheet`, `blank`). Every underwriting metric accepts a `source`
filter:

- Query param: `source: list[UnderwritingSource]`, repeatable.
- Default when omitted: `adus` and `blank` — every row created in the current
  system.
- Passing all three values includes the 2,021 legacy sheet rows.

`blank` is included by default because blank underwritings move through the
same deal statuses as `adus` rows; only their listing data is hand-typed.

### D3. Every underwriting row counts once (proposed)

Duplicated deals share a `series_id` and differ by `version`. Analytics counts
**every row**, exactly as the underwritings list page does, and does not
collapse a series to one version.

Reasons:

- Each version carries its own `deal_status`, so collapsing would have to pick
  which version's status wins — a rule nobody has agreed on.
- The volume is small (9 Duplicate-button copies in the dev snapshot).
- Metric 25 reports copies separately, so the effect stays visible.

Revisit if copies become common.

### D4. Underwritings are described by their deal status (decided)

There is no grouping of statuses into stages. Every metric works on the 12
`DealStatus` values (plus `NULL`) directly:

- **Breakdowns** return one item per status, labelled and ordered from
  `STATUS_OPTIONS`.
- **Per-group tables** (per market, per price band) carry a per-status
  breakdown, not a per-stage one.
- **Filters** take statuses: `deal_status` is a repeatable query param of
  `DealStatus` values wherever a metric needs to narrow the population.
- **A metric that needs a subset of statuses names the statuses.** The few
  subsets the proposal's definitions require are module-level constants in
  `app/iron_bank/services/analytics/underwriting_analytics_service.py`, written
  as tuples of `DealStatus` members, so the SQL never contains a hand-typed
  status string:

  | Constant | Statuses | Used by | Proposal wording |
  |---|---|---|---|
  | `PRESENTED_STATUSES` | `present_to_clients`, `client_under_contract` | win rate, conversion, quality, tag mix | "presented + under contract" — a deal under contract was presented first |
  | `WON_STATUSES` | `client_under_contract` | win rate, conversion | "client under contract" |
  | `DELETED_STATUSES` | `delete_zillow`, `delete_deal` | quality comparison, delete reasons | "deleted deals" |
  | `ANALYSIS_STATUSES` | `analyst_started`, `analyst_completed`, `re_forecast_revenue`, `awaiting_realtor_details`, `maybe` | wasted analyst effort (metric 12) | "deals that went off the market while still in analysis" |

  These are filters for specific metrics, not categories: no response ever
  returns a constant's name as a key, and a status can belong to more than one
  constant (`client_under_contract` is in both `PRESENTED_STATUSES` and
  `WON_STATUSES`).
- **"Still in the pipeline"** (metric 23) reuses the existing
  `TERMINAL_DEAL_STATUSES` from `deal_status_service.py`: a deal is live when
  its status is set and not terminal. That set is derived from
  `DEAL_STATUS_TRANSITIONS`, so it follows the workflow automatically.

A test asserts every constant contains only `DealStatus` members.

### D5. "Off the market" reuses `NOT_PENDING_HOME_STATUSES`

A listing is off the market when
`COALESCE(home_status, '') NOT IN NOT_PENDING_HOME_STATUSES`
(`("FOR_SALE", "OTHER")`, defined in
`app/iron_bank/repositories/underwriting_repository.py`). This is the same rule
`property_pending` is derived from, so the dashboard and the underwritings list
agree on what "pending" means.

The off-market metrics join to `zillow.scheduled_listings` live instead of
reading `Underwriting.property_pending`, because metric 10 needs the raw
`home_status` for its split and the flag is only as fresh as its last sync. All
three metrics in the endpoint use the same join, so they stay consistent with
each other.

### D6. Dates are whole UTC days on a named column

Every date filter is a pair of `date` params named after the column it reads
(`added_from`/`added_to` on `deal_added`, `created_from`/`created_to` on
`created_at`). Both ends are inclusive and anchored to UTC midnight, using the
shared helper proposed in
[Shared date-range helper](#shared-date-range-helper). Weekly buckets start on
Monday (`date_trunc('week', ...)` in Postgres).

## Where each query lives

The rule from `CLAUDE.md`, applied per metric:

```text
Does the metric read only one domain's tables?
  yes -> that domain's analytics repository + analytics service + schema
  no  -> does it need a SQL join across domains?
           yes -> app/analytics/repositories/ (read-only)
           no  -> each domain answers its half; AnalyticsController composes
                  them into a schema in app/analytics/schemas/
```

| Location | Holds |
|---|---|
| `app/iron_bank/repositories/underwriting_analytics_repository.py` | Aggregates over `iron_bank.underwritings` and `iron_bank.jobs` |
| `app/iron_bank/services/analytics/underwriting_analytics_service.py` | Labels, status subsets (D4), ordering, rates |
| `app/iron_bank/schemas/underwriting_analytics.py` | Underwriting-only response schemas |
| `app/zillow/repositories/listing_analytics_repository.py` | Aggregates over `zillow.scheduled_listings` and `zillow.scheduled_presets` |
| `app/zillow/services/listing_analytics_service.py` | Labels, ordering, gap filling |
| `app/zillow/schemas/listing_analytics.py` | Listing-only response schemas |
| `app/analytics/repositories/pipeline_analytics_repository.py` (new) | Listing ⋈ underwriting joins |
| `app/analytics/services/pipeline_analytics_service.py` (new) | Shaping, ordering and rates for the joined metrics. **Extends the `CLAUDE.md` rule**, which lists only controller, router, schemas and repositories for `app/analytics/`; update that line when this lands. The alternative — shaping inside `AnalyticsController` — would make the controller the only one in the codebase holding business logic. |
| `app/analytics/schemas/` | Composed and joined response schemas |
| `app/analytics/controllers/analytics_controller.py` | Validation, composition, market labels |

The joined metrics need the status labels, the `STATUS_OPTIONS` order and the
D4 constants too. `app/analytics/` may import them from iron_bank: it is the
composition layer, and already imports iron_bank services and schemas.

Labels from other domains:

- **Market names** come from `MarketService.get_all_summary()` (markets domain,
  returns `id` and `market_name`), called by `AnalyticsController`. Domain
  repositories return `market_id` only; iron_bank must not import the markets
  domain.
- **Tag labels** (metric 24) come from `ReferenceDataService.get_label_map()`
  in `app/core/`, which any domain may call.
- **Preset names** come from `zillow.scheduled_presets.name`, read by the zillow
  analytics repository.

## Shared conventions

### Filters

| Param | Applies to | Notes |
|---|---|---|
| `market_id` | underwriting and cross-domain endpoints | D1 |
| `preset_id` | listing endpoints and endpoints grouped by listing | D1 |
| `source` | underwriting and cross-domain endpoints | D2, default `adus`+`blank` |
| `deal_status` | endpoints that narrow by status | D4, repeatable |
| `analyst_id` | underwriting endpoints where it makes sense | As in `deal-status-breakdown` |
| `<column>_from`, `<column>_to` | every endpoint | D6 |
| `granularity` | time-series endpoints | `day` or `week`, default `week` |

A reversed range returns `400` through the existing
`AnalyticsController._validate_range`. Any other failure is logged and returns
`500`, matching the existing controller methods.

### Response shapes

Three shapes cover every endpoint. Reusing them keeps the frontend's chart
components generic.

**Breakdown** — counts per category (statuses, bands, tags):

```python
class BreakdownItem(BaseModel):
    key: str | None      # stable slug; None = unknown/unset
    label: str           # display text
    count: int

class Breakdown(BaseModel):
    total: int
    items: list[BreakdownItem]
```

**Time series** — counts per day or week:

```python
class SeriesPoint(BaseModel):
    period_start: date
    count: int

class Series(BaseModel):
    key: str | None
    label: str
    points: list[SeriesPoint]
```

**Per-group table** — one row per market or preset, with several numbers:

```python
class GroupRow(BaseModel):
    key: str | None      # market_id / preset_id as a string; None = unassigned
    label: str
    ...                  # metric-specific numeric fields
```

`DealStatusBreakdown` and `HomeStatusBreakdown` both move to the **Breakdown**
shape (see [Changes to existing endpoints](#changes-to-existing-endpoints)).
Shared shapes live in a new `app/core/analytics/schemas.py` so both domains
can use them without importing each other. The `app/core/analytics/` package
follows the precedent of `app/core/reference_data/` and
`app/core/discussions/`: shared, domain-free, and never importing a domain.

Rates are returned as fractions between 0 and 1 (`0.126`, not `12.6`) with the
numerator and denominator alongside, so the frontend never divides and a rate
over zero items is `null`, not `0`.

## Ordering

Every list in every response is returned in its final display order. The order
is part of the API contract: the frontend renders lists as received and never
re-sorts them. This section explains why, what the rules are, and what changes
in the two existing endpoints.

### Why the backend owns ordering

- **One definition.** If each chart sorts on the client, the web dashboard, a
  later mobile view and any CSV export each implement the rule, and they drift.
- **The backend knows the domain.** Workflow order for deal statuses lives in
  `STATUS_OPTIONS`; bucket order for price bands lives with the band
  definitions. The frontend would have to duplicate both.
- **Testable.** Ordering is asserted in service tests like
  `test_breakdown_sorts_by_count_desc` already does, instead of being
  discovered visually.

Ordering is applied **in the service layer, in Python**, after the repository
returns rows. Repositories may add `ORDER BY` for their own reasons, but the
service never relies on it, because zero-filling and merging (below) change the
list after the query.

### What is wrong today

The two existing endpoints use different rules, and each has a gap.

`deal-status-breakdown` (iron_bank) sorts by workflow position from
`STATUS_OPTIONS`, then unknown statuses, then `NULL`. The order is right, but
it **only returns statuses that have rows**. Filter to one analyst and
"Awaiting Realtor Details" disappears from the response, so the chart's x-axis
changes shape between filters and two charts side by side do not line up. The
proposal asks for a "bar chart of all 12 statuses".

`home-status-breakdown` (zillow) sorts by count, descending. That is a
reasonable rule for an open set of raw Zillow values, but:

- **Ties are not deterministic.** Python's sort is stable, so equal counts keep
  the order the database returned them in, and Postgres does not promise a
  `GROUP BY` order. Two identical requests can return tied statuses in
  different orders, which makes a chart flicker on refresh and makes snapshot
  tests flaky.
- **Unknown is sorted like a real value.** The merged `NULL`/`""` bucket lands
  wherever its count puts it — first, if most listings have no status yet. In
  `deal-status-breakdown` the unknown bucket is always last. The same concept
  sits in different places in two adjacent charts.

### The rules

Choose the rule by **what kind of category** the list holds, not by endpoint.

**Rule 1 — Ordered categories: fixed order, every category present.**
For categories with a natural sequence: deal statuses (workflow order), price
bands, the automated/manual split, and any future age buckets.

- Order by the category's defined position: `STATUS_OPTIONS` order for
  statuses, low-to-high for bands.
- **Fill zeros.** Every known category is returned, with `count: 0` when there
  are no rows. The list's length and order never change with filters.
- When a `deal_status` filter narrows the population, only the requested
  statuses are zero-filled — a chart of "presented deals" lists
  `present_to_clients` and `client_under_contract`, not all 12.
- Values the code does not know (e.g. a status a migration added before the
  enum was updated) come after the known ones, ordered by key, so they are
  visible rather than dropped.
- The unknown/unset item (`key: None`) is last, and only present when its
  count is above zero.

Example — `deal-status-breakdown?analyst_id=7`:

```json
{
  "total": 12,
  "items": [
    {"key": "template_generated", "label": "Template Generated", "count": 4},
    {"key": "analyst_started",    "label": "Analyst Started",    "count": 0},
    {"key": "analyst_completed",  "label": "Analyst Completed",  "count": 5},
    "... every other status, in STATUS_OPTIONS order, zeros included ...",
    {"key": null,                 "label": "No Status",          "count": 3}
  ]
}
```

**Rule 2 — Open categories: count descending, key as tiebreaker.**
For sets the code does not define in advance: raw Zillow `home_status`, tag
values, job types.

- Order by `count` descending, then by `key` ascending. The tiebreaker makes
  the order deterministic for identical data.
- No zero-filling — there is no fixed list to fill from.
- The unknown item (`key: None`) is last regardless of its count, same as
  Rule 1.

**Rule 3 — Rankings: value descending, label then key as tiebreakers, unassigned last.**
For per-group tables: markets, presets, analysts.

- Order by the endpoint's primary number descending (e.g. `underwritten` for
  `market-breakdown`), then by `label` ascending, then by `key`. The label
  tiebreaker gives readers an alphabetical order among equals; the key breaks
  ties between two markets with the same name.
- The "unassigned" row (no `market_id`, no preset) is last.
- An endpoint may accept `sort` (one of its numeric fields) to change the
  primary number. The tiebreakers stay the same.

**Rule 4 — Time series: chronological, gaps filled.**
For anything bucketed by day or week.

- `period_start` ascending.
- Every period between the requested `from` and `to` is present, with
  `count: 0` for empty periods, so a line chart never draws a straight line
  across a missing week. When `from` is omitted, the series starts at the first
  period with data.
- Multiple series in one response follow Rule 3 between themselves, by total
  count.

### Where the rules live

Implement the rules once, as helpers in `app/core/analytics/ordering.py`, next
to the shared schemas, and call them from every analytics service:

```python
def order_fixed(items, *, known_order: Sequence[str]) -> list[BreakdownItem]: ...
def order_open(items) -> list[BreakdownItem]: ...
def order_ranked(rows, *, by: str) -> list[GroupRow]: ...
def fill_series(points, *, start: date, end: date, granularity: Granularity) -> list[SeriesPoint]: ...
```

`order_fixed` takes the known order explicitly, so `STATUS_OPTIONS` stays in
iron_bank and `app/core/` stays free of domain knowledge.

### Tests for ordering

For each endpoint's service:

- **Rule 1:** a filter that returns no rows for one status still returns that
  status with `count: 0` in its workflow position; with a `deal_status` filter,
  only the requested statuses appear; an unknown status sorts after the known
  ones; `None` is last.
- **Rule 2:** two values with equal counts come back in key order regardless of
  the order the fake repository yields them in (feed them reversed to prove
  it); `None` with the highest count is still last.
- **Rule 3:** ties broken by label, then key; unassigned row last.
- **Rule 4:** a range with an empty middle week returns that week with zero.

## Endpoints

15 endpoints: 2 existing (changed), 13 new. All are `GET` under `/analytics`.

| # | Path | Lives in | Metrics |
|---|---|---|---|
| 1 | `/listings/home-status-breakdown` | zillow (existing) | supports 10 |
| 2 | `/listings/intake` | zillow | 1 |
| 3 | `/underwritings/deal-status-breakdown` | iron_bank (existing) | 5 |
| 4 | `/underwritings/template-progress` | iron_bank | 7 |
| 5 | `/underwritings/market-breakdown` | iron_bank + market labels | 15, 18, 19 |
| 6 | `/underwritings/price-bands` | iron_bank | 20 |
| 7 | `/underwritings/quality-comparison` | iron_bank | 21 |
| 8 | `/underwritings/delete-reasons` | iron_bank + market labels | 22 |
| 9 | `/underwritings/tag-mix` | iron_bank + reference labels | 24 |
| 10 | `/underwritings/duplicates` | iron_bank | 25 |
| 11 | `/automation` | composed: iron_bank + zillow | 3, 4 |
| 12 | `/data-completeness` | composed: iron_bank + zillow | 26 |
| 13 | `/pipeline/coverage` | joined (`app/analytics/repositories/`) | 2 |
| 14 | `/pipeline/off-market` | joined | 10, 11, 12 |
| 15 | `/pipeline/price-drops` | joined | 23 |

Paths under `/underwritings` and `/listings` are single-domain; paths without
a resource prefix are composed from two domain services; paths under
`/pipeline` are SQL joins across domains.

Common underwriting filters below means `market_id`, `analyst_id`, `source`,
`added_from`, `added_to` (D1, D2, D6).

### 1. `GET /analytics/listings/home-status-breakdown` (existing, changed)

- **Filters:** `preset_id`, `created_from`, `created_to`. `market_id` removed (D1).
- **Query:** unchanged apart from the filter: `COUNT(*)` grouped by
  `home_status` on `zillow.scheduled_listings`.
- **Response:** `Breakdown`. `key` is the raw `home_status`, `label` a
  title-cased version (`RECENTLY_SOLD` → `Recently Sold`). `""` and `NULL` merge
  into `key: None`, as today.
- **Order:** Rule 2.

### 2. `GET /analytics/listings/intake` — metric 1

- **Filters:** `preset_id`, `created_from`, `created_to`, `granularity`,
  `group_by` (`none` | `preset`, default `none`).
- **Query:** `COUNT(*)` grouped by
  `date_trunc(granularity, created_at AT TIME ZONE 'UTC')`, and by `preset_id`
  when `group_by=preset`. `created_at` is the listing's first-seen time.
- **Response:** `list[Series]` — one series (`key: None`, label "All listings")
  or one per preset, labelled with the preset name.
- **Order:** Rule 4 within each series; Rule 3 between series.

### 3. `GET /analytics/underwritings/deal-status-breakdown` (existing, changed) — metric 5

- **Filters:** common underwriting filters (adds `source`), `deal_status`.
- **Query:** unchanged apart from the new filters.
- **Response:** `Breakdown` (renames `statuses` → `items`).
- **Order:** Rule 1 with `STATUS_OPTIONS` order — **adds zero-filling**.

### 4. `GET /analytics/underwritings/template-progress` — metric 7

The proposal says "per weekly listing group". Grouping by the listing's week
would need a join to zillow; grouping by the underwriting's `deal_added` week
answers the same question ("of the deals created that week, how many got past
the template?") from iron_bank alone. This design uses `deal_added`; see Open
questions.

- **Filters:** common underwriting filters, `granularity`.
- **Query:** per `date_trunc(granularity, deal_added)`: `COUNT(*)` as
  `created`, and `COUNT(*) FILTER (WHERE deal_status IS NOT NULL AND
  deal_status <> 'template_generated')` as `past_template`.
- **Response:**

  ```python
  class TemplateProgressPoint(BaseModel):
      period_start: date
      created: int
      past_template: int
      share: float | None   # past_template / created; None when created == 0
  ```

- **Order:** Rule 4.

### 5. `GET /analytics/underwritings/market-breakdown` — metrics 15, 18, 19

One query answers all three metrics per market, plus an overall row.

- **Filters:** `analyst_id`, `source`, `added_from`, `added_to`,
  `sort` (default `underwritten`). No `market_id` — this endpoint is the
  per-market view.
- **Query:** grouped by `market_id` and `deal_status`, `COUNT(*)`. The service
  pivots the rows into one row per market.
- **Response:**

  ```python
  class MarketRow(GroupRow):
      underwritten: int                  # all rows
      by_status: list[BreakdownItem]     # metric 18, Rule 1 order, zeros filled
      presented: int                     # deal_status in PRESENTED_STATUSES
      won: int                           # deal_status in WON_STATUSES
      presented_rate: float | None       # presented / underwritten (metric 19)
      win_rate: float | None             # won / presented (metrics 15, 19)

  class MarketBreakdown(BaseModel):
      overall: MarketRow                 # key None, label "All markets" (metric 15)
      markets: list[MarketRow]
  ```

  `presented` includes `client_under_contract` because a deal under contract
  was presented first (D4). This matches the proposal's
  "under contract ÷ (presented + under contract)".
- **Labels:** `AnalyticsController` maps `market_id` → `market_name` through
  `MarketService.get_all_summary()`. Rows with no `market_id` get
  `label: "Unassigned"`.
- **Order:** markets by Rule 3 on `sort`; `by_status` by Rule 1; `overall` is a
  separate field, not part of the list.

### 6. `GET /analytics/underwritings/price-bands` — metric 20

- **Filters:** common underwriting filters, `deal_status`.
- **Bands:** `under_300k`, `300k_500k`, `500k_750k`, `750k_1m`, `over_1m`, on
  `purchase_price` (lower bound inclusive). Defined once as a tuple of
  `(key, label, lower, upper)` in the iron_bank analytics service and rendered
  as a `CASE` expression. `NULL` price → `key: None`.
- **Query:** `COUNT(*)` grouped by band and `deal_status`.
- **Response:**

  ```python
  class PriceBandRow(BaseModel):
      key: str | None
      label: str
      total: int
      by_status: list[BreakdownItem]
  ```

- **Order:** bands by Rule 1 in band order, zeros filled, `None` last;
  `by_status` by Rule 1.

### 7. `GET /analytics/underwritings/quality-comparison` — metric 21

- **Filters:** common underwriting filters.
- **Groups:** `presented` (`PRESENTED_STATUSES`) vs `deleted`
  (`DELETED_STATUSES`). Each group reports the statuses it covers, so the
  response says exactly which deals it compares.
- **Query:** per group, `percentile_cont(0.5) WITHIN GROUP (ORDER BY …)` on
  `m_cash_on_cash`, `deal_score`, `total_oop`, plus `COUNT(column)` for each, so
  each median reports how many non-null values it is based on.
- **Response:**

  ```python
  class MedianValue(BaseModel):
      value: float | None
      sample_size: int

  class QualityGroup(BaseModel):
      key: Literal["presented", "deleted"]
      label: str
      statuses: list[str]               # the DealStatus values in this group
      deals: int
      median_cash_on_cash: MedianValue
      median_deal_score: MedianValue
      median_total_oop: MedianValue
  ```

- **Order:** fixed: `presented`, then `deleted`.

### 8. `GET /analytics/underwritings/delete-reasons` — metric 22

- **Filters:** common underwriting filters minus `market_id`.
- **Query:** `COUNT(*)` grouped by `market_id` and `deal_status`, restricted to
  `DELETED_STATUSES`, plus an overall row.
- **Response:** `GroupRow` per market with `by_status` (a `Breakdown` of
  `delete_zillow` — "bad listing" — and `delete_deal` — "bad numbers") and
  `total`; plus `overall`.
- **Order:** markets by Rule 3 on `total`; `by_status` by Rule 1.
- The proposal also asks for a split by preset. That needs the listing's
  `preset_id`, so it is a cross-domain join; left as an open question.

### 9. `GET /analytics/underwritings/tag-mix` — metric 24

- **Filters:** common underwriting filters, `deal_status` (default
  `PRESENTED_STATUSES`).
- **Query:** one aggregate per tag field:
  - Multi-select (`core_value_driver`, `market_type`, `text[]`):
    `unnest(column)` then `COUNT(*)` per slug.
  - Single-select (`primary_guest_avatar`): `COUNT(*)` grouped by the column.
- **Labels:** slugs are resolved through `ReferenceDataService.get_label_map()`
  (`(set_code, key) → label`). An unresolved slug uses the slug as its label.
- **Response:** `dict[str, Breakdown]` keyed by field name. For multi-select
  fields an item's `count` is the number of deals carrying that tag, so items
  can sum to more than `total` (number of deals); say so in the schema
  docstring.
- **Order:** Rule 2 within each field.

### 10. `GET /analytics/underwritings/duplicates` — metric 25

- **Filters:** common underwriting filters.
- **Query:** two numbers from iron_bank alone:
  - Same property underwritten more than once: `zpid`s with more than one
    distinct `series_id`, and the number of rows involved.
  - Intentional copies: rows with `copied_from_id IS NOT NULL`.
- **Response:**

  ```python
  class Duplicates(BaseModel):
      properties_underwritten_repeatedly: int
      underwritings_on_those_properties: int
      duplicate_button_copies: int
  ```

### 11. `GET /analytics/automation` — metrics 3 and 4 (composed)

Three independent answers composed by `AnalyticsController` into one schema in
`app/analytics/schemas/automation.py`. No SQL join.

- **Filters:** `created_from`, `created_to` (applied to underwritings'
  `deal_added` and jobs' `created_at`), `market_id` and `source` (underwritings
  only).
- **Underwritings (iron_bank):** `Breakdown` of `is_automated` —
  `automated`, `manual`, `None` (unknown). Order: Rule 1 (`automated`,
  `manual`), unknown last.
- **Jobs (iron_bank, `iron_bank.jobs`):** per `job_type`, counts by `status`
  (`queued`, `running`, `succeeded`, `failed` — the values the job workflows
  write) and the latest `finished_at`. Order: Rule 2 by total jobs.
- **Presets (zillow, `zillow.scheduled_presets`):** per active preset,
  `last_run`, `next_run`, `last_full_run`, and whether it is overdue
  (`next_run < now()`). Order: overdue first, then by `last_run` ascending
  (oldest run first), then name — the presets most in need of attention lead.

### 12. `GET /analytics/data-completeness` — metric 26 (composed)

- **Underwritings (iron_bank):** out of all rows matching the common
  underwriting filters, how many have `market_id IS NULL`,
  `analyst_id IS NULL`, `purchase_price IS NULL`, `deal_status IS NULL`.
- **Listings (zillow):** listings with `keep_updated` true and
  `last_seen < now() - stale_after_days` (param, default 14), grouped by preset.
- **Response:** `{ underwritings: {total, missing_market, missing_analyst,
  missing_price, missing_status}, stale_listings: {total, presets:
  list[GroupRow]} }`.
- **Order:** presets by Rule 3 on stale count.

### 13. `GET /analytics/pipeline/coverage` — metric 2 (joined)

- **Filters:** `preset_id`, `created_from`, `created_to` on the listing's
  `created_at`, `source` (applies to the underwritings counted). No
  `market_id` — the denominator is all listings, which have no underwriting
  market (D1).
- **Query:** listings in range, left-joined to their earliest underwriting
  (`MIN(deal_added)` per `zpid`):
  - `listings`: `COUNT(*)`
  - `underwritten`: listings with at least one underwriting
  - `median_days_to_underwrite`: `percentile_cont(0.5)` of
    `MIN(deal_added) - listing.created_at`, in days
- **Response:** an overall row plus one `GroupRow` per preset with those fields
  and `coverage` (`underwritten / listings`).
- **Order:** Rule 3 by `listings`.

### 14. `GET /analytics/pipeline/off-market` — metrics 10, 11, 12 (joined)

- **Filters:** common underwriting filters, `deal_status`.
- **Query:** underwritings joined to `zillow.scheduled_listings` on `zpid`,
  keeping rows that are off the market (D5). Grouped by `deal_status` and raw
  `home_status`.
- **Response:**

  ```python
  class OffMarketStatusRow(BaseModel):
      key: str | None                     # deal_status
      label: str
      off_market: int
      by_home_status: list[BreakdownItem] # PENDING / SOLD / ...

  class OffMarket(BaseModel):
      by_status: list[OffMarketStatusRow] # metric 10
      missed_deals: int                   # metric 11: present_to_clients and off market
      presented_total: int                # denominator: all present_to_clients deals
      wasted_analysis: int                # metric 12: ANALYSIS_STATUSES and off market
  ```

  `missed_deals` counts `present_to_clients` only, not `PRESENTED_STATUSES`:
  a deal under contract that went off the market is a win, not a miss.
- **Order:** `by_status` by Rule 1 (`STATUS_OPTIONS` order); each row's
  `by_home_status` by Rule 2.

### 15. `GET /analytics/pipeline/price-drops` — metric 23 (joined)

- **Filters:** common underwriting filters, `changed_from`, `changed_to` on
  `scheduled_listing_details.price_change_date`.
- **Query:** underwritings still in the pipeline (`deal_status IS NOT NULL` and
  not in `TERMINAL_DEAL_STATUSES`, D4) joined to
  `zillow.scheduled_listing_details` on `zpid`, where `price_change < 0`. This
  assumes Zillow stores a drop as a negative `price_change`; verify against a
  few rows' `price_history` before building.
- **Response:** `Breakdown` by `deal_status` of deals with a price drop, plus
  `median_drop_pct` (`price_change / (price - price_change)`) with its sample
  size.
- **Order:** Rule 1 (`STATUS_OPTIONS` order), zero-filled over the non-terminal
  statuses only.

## Changes to existing endpoints

| Endpoint | Change | Why |
|---|---|---|
| `home-status-breakdown` | `market_id` → `preset_id`; drop the preset join for market | D1 |
| `home-status-breakdown` | Response becomes `Breakdown` (`home_status` → `key`, adds `label`, `statuses` → `items`) | Shared shape |
| `home-status-breakdown` | Unknown bucket always last; ties broken by key | Ordering Rule 2 |
| `deal-status-breakdown` | Adds `source` filter (default `adus`+`blank`) and `deal_status` filter | D2, D4 |
| `deal-status-breakdown` | Response becomes `Breakdown` (`statuses` → `items`) | Shared shape |
| `deal-status-breakdown` | Zero-fills every status in `STATUS_OPTIONS` | Ordering Rule 1 |

The tests in `tests/analytics/` change with them:
`test_breakdown_sorts_by_count_desc` gains a tie case, and
`test_repository_joins_preset_only_when_filtering_by_market` becomes a
`preset_id` filter test.

## Shared date-range helper

### Problem

`UnderwritingAnalyticsRepository` imports `_date_range_conditions` from
`underwriting_repository.py`. The leading underscore marks it as private to
that module, so the analytics repository depends on an implementation detail
of another file: a refactor of the list repository can break analytics without
any hint that the helper had other callers.

`ListingAnalyticsRepository` in the zillow domain needs the same logic, but
cannot import it — that would be a cross-domain import, which `CLAUDE.md`
forbids. So it re-implements the same half-open UTC-day range inline:

```python
# app/zillow/repositories/listing_analytics_repository.py
if created_from is not None:
    query = query.where(
        ScheduledListing.created_at
        >= datetime.combine(created_from, time.min, tzinfo=timezone.utc)
    )
if created_to is not None:
    query = query.where(
        ScheduledListing.created_at
        < datetime.combine(created_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
    )
```

Two copies of a subtle rule (exclusive next-day upper bound, explicit UTC
anchor) already exist after two endpoints. This design adds roughly 15 more
date filters across three locations, so the copies would multiply.

### Proposal

Move the helper to `app/core/`, which `CLAUDE.md` names as the home for logic
shared across domains, and make it public.

New module `app/core/query_filters.py`:

```python
def date_range_conditions(column, minimum: date | None, maximum: date | None) -> list:
    """Half-open, UTC-anchored day-range conditions for a ``timestamptz`` column.

    (docstring carried over unchanged from underwriting_repository.py)
    """


def numeric_range_conditions(column, minimum, maximum) -> list:
    """Inclusive ``minimum <= column <= maximum`` conditions, either end open."""
```

`_numeric_range_conditions` moves with it: it is its documented sibling, and
analytics endpoints with numeric filters (price bands, a future
`min_price`/`max_price`) would hit the same problem.

Callers after the move:

| File | Today | After |
|---|---|---|
| `app/iron_bank/repositories/underwriting_repository.py` | defines `_date_range_conditions`, `_numeric_range_conditions`; 4 call sites | imports both from `app.core.query_filters` |
| `app/iron_bank/repositories/underwriting_analytics_repository.py` | imports the private helper | imports from `app.core.query_filters` |
| `app/zillow/repositories/listing_analytics_repository.py` | inline copy | imports from `app.core.query_filters` |
| `app/analytics/repositories/pipeline_analytics_repository.py` (new) | — | imports from `app.core.query_filters` |

Notes:

- **No behaviour change.** Bodies and docstrings move verbatim; the module is
  pure functions over SQLAlchemy columns with no dependency on any domain.
- **Do it first**, as its own change, before the new endpoints. It is a small,
  mechanical refactor whose safety is easy to verify on its own (existing list
  filter tests plus the analytics tests must pass unchanged), and every new
  endpoint then starts from the shared helper.
- **Tests:** move the helper's unit cases (min == max returns that day; upper
  bound is exclusive of the next day; bounds are UTC regardless of session
  time zone) to `tests/core/test_query_filters.py`.
- **Name:** `query_filters.py` describes what it holds (WHERE-clause builders).
  `app/core/` has no `utils.py`, and this design does not start one.

## Build order

1. Move the date-range helper to `app/core/query_filters.py`.
2. Add shared schemas (`Breakdown`, `Series`, `GroupRow`) and the ordering
   helpers in `app/core/analytics/`; migrate the two existing endpoints to them.
3. Add the `source` and `deal_status` filters and the D4 status constants.
4. iron_bank-only endpoints (3–10 in the table).
5. Composed endpoints (`automation`, `data-completeness`).
6. Joined endpoints (`pipeline/*`), in a new
   `app/analytics/repositories/pipeline_analytics_repository.py`.

## Testing

Following the pattern in `tests/analytics/`:

- **Repository tests** compile the query with the Postgres dialect against a
  capturing fake session and assert on the SQL: filters present only when
  passed, `source` default applied, status constants rendered as `IN (...)`
  lists.
- **Service tests** feed a fake repository fixed rows and assert on labels,
  rates (including `None` on a zero denominator), zero-filling and ordering
  (see [Tests for ordering](#tests-for-ordering)).
- **Controller tests** cover the `400` on a reversed range, `500` on a service
  error, and market-label composition.
- **Definition tests:** every D4 constant contains only `DealStatus` members;
  price bands are contiguous and non-overlapping.
- **One reconciliation check** against the dev database (manual or a marked
  test): `pipeline/off-market` with `source` = all should land near the
  proposal's 766 / 931 and 134 under contract. Differences are expected where
  D2, D5 or a newer snapshot change the population, but a large gap means a
  definition is wrong.

## Open questions

1. **D2 default** — confirm `blank` belongs with `adus` in the default.
2. **D4 `ANALYSIS_STATUSES`** — confirm which statuses count as "still in
   analysis" for metric 12. Proposed: `analyst_started`, `analyst_completed`,
   `re_forecast_revenue`, `awaiting_realtor_details`, `maybe`.
3. **Metric 7 grouping** — `deal_added` week (this design) or the listing's
   first-seen week (needs a join)?
4. **Metric 21 cash-on-cash** — `m_cash_on_cash` (mid case) assumed; confirm
   it is the figure leadership means.
5. **Metric 22 by preset** — worth a joined endpoint, or is per-market enough?
6. **Price-drop sign** — confirm `price_change` is negative for a drop
   (metric 23).
7. **Metric 9** — missing from the proposal.
