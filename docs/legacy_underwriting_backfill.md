# Legacy underwriting backfill

Two scripts keep `iron_bank.underwritings` in sync with the "Underwritten Properties" Google Sheet and enrich it with Zillow data the sheet doesn't
carry:

- [`scripts/backfill_legacy_underwritings.py`](../scripts/backfill_legacy_underwritings.py)
  — reads the sheet, inserts new deals, and refreshes existing ones.
- [`scripts/backfill_zillow_property.py`](../scripts/backfill_zillow_property.py)
  — scrapes Zillow for deals the sheet's own data can't fully describe.

Run them in that order: a deal needs to exist (first script) before its
Zillow listing can be enriched (second script).

## `backfill_legacy_underwritings.py`

### Data sources

The sheet has two kinds of tabs, read via `read_workbook()` (a local xlsx
export) or `read_google_sheet()` (live, via the Sheets API — needs
`GOOGLE_SERVICE_ACCOUNT_CREDENTIALS` in the environment, a service account
key as inline JSON):

- **Tracking tabs** (`Main_Sheet`, `Delete_Properties`, `ClientShown_Properties`)
  — one summary row per deal, keyed by the `Link` column. Precedence when a
  link appears in more than one: Main_Sheet > ClientShown_Properties >
  Delete_Properties.
- **Individual deal tabs** — one worksheet per deal, named by its sheet
  number (`"233"`, `"1937"`, ...), parsed by section label rather than fixed
  coordinates because the template has shifted many times across the
  sheet's history.

A deal can have a summary row only, a deal tab only, or both. `build_deal()`
merges whichever exist; when both are present, most fields prefer the
summary row and fall back to the deal tab (`purchase_price`, `analyst_name`,
`bedrooms`/`bathrooms`).

### Header drift: aliases + hard failures

The sheet's column headers and section labels have been renamed multiple
times (`Deal_Status` → `Status`, `Cash Needed` → `OOP`,
`Optimization List (Estimate)` → `Game Plan / Blue Print (Estimate)`, ...).
Two different strictness levels handle this, deliberately:

- **Summary-row fields** (`SUMMARY_FIELD_ALIASES`, `TAB_OPTIONAL_FIELDS`):
  each field lists every header name it's known to go by. If a tracking
  tab's header row doesn't match *any* alias for a required field, parsing
  raises immediately — a renamed header that's silently unmatched is exactly
  what let `deal_status` default to "no status" for every row, undetected,
  the last time this happened. Some fields are legitimately absent on some
  tabs by design (`ClientShown_Properties` never tracked approver/turnkey/
  bedroom info) — those are listed in `TAB_OPTIONAL_FIELDS` and stay silent.
- **Deal-tab sections**: `Purchase Details`, `Optimization List`, and
  `Operating Expenses` are expected on *every* deal tab regardless of
  template version, so their parsers (`_parse_purchase_details`,
  `_parse_optimization_items`, `_parse_operating_expenses`) raise
  `ValueError` naming the sheet number if the header can't be found —
  crashing the whole run rather than inserting a deal with an empty section.
  `_parse_optimization_items` also tries multiple header aliases
  (`_find_row_by_any_prefix`) before giving up, the same pattern as the
  summary-row fields. Every *other* deal-tab section (construction loan
  block, cleaning cost, comp set, analyst notes, taxes, ...) is genuinely
  version-specific — their absence is normal, so they stay soft and just
  return empty/`None`.

If the sheet renames something again, the fix is the same either way: add
the new header text as another alias (or another prefix in
`_find_row_by_any_prefix`'s tuple), not to loosen the validation.

### Other parsing notes

- **`bedrooms`/`bathrooms`** come from a free-text "Property Details" blob
  (the same cell the tracking tab and the deal tab each carry a copy of, not
  always in sync) via `parse_bed_bath()`, which looks for a
  `"Bed / Bath (Projected): X / Y"` line in varying formats. The summary
  row's copy is tried first, then the deal tab's, as a fallback. A bare
  number with no such line (an older sheet convention) resolves to neither
  field rather than guessing.
- **`listing_url`** is read from hyperlinks on the tracking tabs and deal
  tabs (`extract_listing_urls()` / `read_google_sheet()`'s listing-url
  collection), with the same tab-precedence as summary rows.
- **`zpid`** is extracted from any `listing_url` containing `_zpid` via
  regex (`extract_zpid()`), but only written onto the row once confirmed
  against `zillow.scheduled_listings` — a zpid parsed from an old URL that's
  no longer in that table stays unset rather than pointing at a listing that
  doesn't exist.
- **Analyst/approver matching** (`build_user_matcher()`) matches a sheet
  label like `"Taylor J"` against `users.users` by `"first last"` or
  `"first lastinitial"`, plus a bare-first-name key — but only when exactly
  one *named* user shares that first name, and never via a placeholder
  (`legacy_%` clerk_id) user, so an old placeholder can never win the match
  over the real person it was standing in for. Labels that still don't
  resolve are reported (not silently defaulted, and no new placeholder user
  is created) via `NICKNAME_OVERRIDES` gaps in the run's warnings.

### Modes

| Flag | Behavior |
|---|---|
| *(none)* | Inserts deals whose `sheet_number` isn't already in the DB. Existing ones are skipped (a partial unique index also enforces this DB-side). |
| `--update` | Deletes and reinserts deals in `--range` that already exist. Gets a fresh `id`, `created_at`, and `zillow_property` is lost (it isn't sheet data) — use this only after a parser fix or a fresh export, not for routine syncing. |
| `--refresh` | Updates already-imported deals **in place** — same `id`, `created_at` untouched, `zillow_property` untouched. This is the routine "the sheet changed, sync it" mode. See safety nets below. |
| `--backfill-zpids` | Targeted `UPDATE`: fills `zpid` on already-loaded rows from their stored `listing_url`, for rows that didn't have a confirmed match at insert time but do now. |
| `--dry-run` | Parse and report only. Combined with `--refresh`, it still queries the DB (to know what "already exists" means) but writes nothing — this is the one exception to `--dry-run`'s usual "no database access" guarantee. |
| `--range LOW:HIGH` | Restricts to sheet numbers in this inclusive range. Applies to all modes. |

### `--refresh` safety nets

Two situations that came up in practice, both handled by leaving the
existing row alone rather than guessing:

- **No current summary row** (`no_summary`): if a sheet number currently has
  a deal tab but no tracking-tab row, the entire top-level `underwriting`
  update is skipped for that deal (reported under `detail_only`) — only its
  deal-tab-derived detail/tax/line-item data is refreshed. `deal_status`,
  `property_address`, and everything else summary-only stays as it was.
  This exists because a transiently-missing summary previously caused
  `deal_status` to be wrongly reset to "no status" for otherwise-fine deals.
- **`optimization_items`/`operating_expenses` replacement**: these are
  wholesale-replaced with the freshly parsed list on every refresh (not
  merged) — correct once the parser actually finds the section, but this is
  exactly why the section-not-found cases above must raise instead of
  returning `[]`: a soft empty result here would silently wipe real stored
  line items.

A sheet number not yet in the DB at all is reported under `not_found` (not
inserted) — run without `--refresh` for that.

## `backfill_zillow_property.py`

The sheet has no "Bathrooms" column and its "Bedrooms" cell is often blank
or unparseable, and many older deals were never given a `zpid` match at
all. For legacy deals that have **no `zpid`** but **do** have a `zillow.com`
listing URL, this script fills in `uw_details.zillow_property` by scraping
the listing directly, via the same `ZillowPropertyService`
(`app/external_api/services/zillow_property_service.py`) other parts of the
app use.

- Candidates: `source='legacy_sheet'`, `zpid IS NULL`,
  `listing_url ILIKE '%zillow.com%'`, `uw_details.zillow_property IS NULL`
  (or the `uw_details` row doesn't exist yet). Non-Zillow listing URLs
  (Redfin, Airbnb, ...) aren't candidates — the API only knows Zillow.
- Writes the canonical 11-key shape used by every other `zillow_property`
  value in the DB: `id`, `url`, `thumbnail`, `price`, `address`, `bedrooms`,
  `bathrooms`, `area`, `lot_size_sqft`, `original_photos`, `description`.
  `street`/`city`/`state` (which the service also returns) are popped off
  before storing, matching how the rest of the app persists this field.
- Runs strictly **sequentially**, one request at a time, with a delay
  between requests (`--delay`, default 1s) — the upstream API is a real
  scrape and can rate-limit or block on bursts.

| Flag | Behavior |
|---|---|
| *(none)* | Processes every candidate. |
| `--limit N` | Only the first N candidates (ordered by `sheet_number`) — useful for testing before a full run. |
| `--dry-run` | Fetches and reports what *would* be written, without writing. Still calls the external API for each candidate (there's nothing to preview otherwise), so it isn't free or instant. |
| `--delay SECONDS` | Seconds between requests (default `1.0`). |

Not every zpid-less deal is resolvable this way — deals with no
`listing_url` at all, or a malformed one (missing the `_zpid/<id>` segment),
report as `empty` in the run's summary rather than failing the whole batch.

`bedrooms`/`bathrooms` specifically are *not* this script's job once a deal
already has a `zillow_property` or a matched `zpid` — that's
[`scripts/backfill_underwriting_bedrooms.py`](../scripts/backfill_underwriting_bedrooms.py),
a separate, idempotent, set-based script that fills those two columns from
`zillow_property` first and `zillow.scheduled_listings` (via `zpid`)
second, for every underwriting regardless of source. Run that *after* this
script for full coverage — it will pick up whatever this one just scraped.
