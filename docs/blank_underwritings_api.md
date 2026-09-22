# Blank underwritings — `POST /iron-bank/underwritings/blank`

Implementation plan for a second create path: an underwriting started from nothing,
for off-market and word-of-mouth deals that have no Zillow listing.

Backend only. **No Alembic migration** — `underwritings.source` is `String(50)` with a
server default rather than a DB enum, and `uw_operating_expenses.monthly_amount` is
already nullable.

## Why

Today an underwriting can only be created from a listing URL
(`POST /iron-bank/underwritings/from-zillow-url`). Analysts working an off-market deal
have no way to start one — address, size and lot get typed into the worksheet by hand
instead of scraped.

This runs the same seeding pipeline with the Zillow fetch skipped, plus a new
`source = "blank"` value the frontend keys its editable, no-listing hero UI off.

Two findings from tracing what the existing pipeline produces when the inputs a listing
normally supplies are absent shaped the contract:

**`purchase_price` gates the entire financing and tax seed.** `_build_details` only emits
`purchase_details` when a price is present, and `payload["taxes"]` is `None` under the
same condition. Without a price, `build_market_context` fetches the market's config and
the live FRED 30-year rate and then discards both — and nothing persists them or hands
them back later, so the FE would invent its own defaults and blank deals would silently
stop tracking FRED. **Hence `purchase_price` is mandatory on this endpoint.**

**A missing `bedrooms` degrades the sheet badly.** The `(market_id, bedrooms)` opex lookup
misses, so the market's opex row, `cleaning_cost`, `property_taxes` and its `land_value` /
`appreciation` config are all lost — even when the market is known. It is recoverable via
`GET /underwritings/{id}/bedroom-context`, but only if the FE merges everything that
endpoint returns. `bedrooms` stays **optional** pending a product decision; see
[Known gaps](#known-gaps--frontend-contract) for what that costs.

A companion change already on this branch makes `build_opex_expense_rows` seed every
`OPEX_ROWS` row — blank when unresolved — instead of dropping unresolved rows. That is
what makes a sparsely-seeded blank underwriting legible rather than misleading, and it
applies to the Zillow path too.

---

## 1. New enum value

`app/iron_bank/enums.py` — add to `UnderwritingSource`:

```python
BLANK = "blank"
```

The frontend keys `isBlank` off this, so it must round-trip on both the list and detail
endpoints. It does automatically: `source` is on `UnderwritingBase`, which
`UnderwritingRead` extends, and `GetUnderwritingService._parent_data` copies every
`UnderwritingRead` field.

## 2. Request schema

New `app/iron_bank/schemas/create_blank_underwriting.py`:

```python
class CreateBlankUnderwritingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_price: Decimal = Field(..., gt=0)
    market_id: int | None = None
    bedrooms: int | None = Field(default=None, ge=0)
    bathrooms: Decimal | None = None
```

Response is the existing `SaveUnderwritingResult` (`{underwriting_id: int}`) — the same
shape the from-URL endpoint returns.

**Reuse `normalize_absent_market`** from `CreateUnderwritingFromUrlPayload`
(`app/iron_bank/schemas/create_underwriting_from_url.py:16-30`). Clients send `0` from an
unselected market dropdown; without folding it to `None` the value flows through as a real
id and the insert violates the FK to `markets.market_keys_master`. Lift the validator
somewhere shared rather than copying it.

## 3. Payload builder — a second entry point, not a new class

`app/iron_bank/services/non_automated_underwriting_payload_builder.py`

Refactor `build_from_zillow_property` so everything from `purchase_price` downward becomes
a private `_build(...)`, then add `build_blank(...)` alongside it.

*Why not a new `BlankUnderwritingPayloadBuilder`:* `BaseUnderwritingPayloadBuilder` holds
the shared helpers, but ~40 lines of assembly live in this subclass — the cleaning-cost and
property-tax derivation, `_build_details`, the `_build_taxes` gating, the opex and
optimization calls, owner resolution. A sibling class duplicates all of it and drifts.
`PrepareUwDataJob._resolve_market_lookup`'s docstring records that this exact drift already
happened once between the automated and non-automated paths.

*Why not call `build_from_zillow_property` with a synthetic dict:* it takes a non-optional
`listing_url`, pops `street`/`city`/`state`, stamps a `zpid`, and unconditionally writes
`details["zillow_property"] = zillow_property`. Passing a fake property through it makes
the method's own contract a lie for whoever next touches the Zillow path.

`build_blank` sets:

| field | value |
| --- | --- |
| `source` | `UnderwritingSource.BLANK` — **new behaviour**; the Zillow path sets no `source` at all and falls through to the `"adus"` server default |
| `purchase_price`, `bedrooms`, `bathrooms` | from the payload, on the top-level columns **and** mirrored into the blob below |
| `market_id` | `context.get("market_id")` — `None` for a template deal, as today |
| `details.zillow_property` | the full `ZillowProperty` shape, `price` / `bedrooms` / `bathrooms` from the payload and every other key `None` — see below |
| `is_automated` | `False` |
| `listing_url`, `zpid`, `property_address`, `street`, `city`, `state` | `None` |
| `deal_status` | `_DEFAULT_DEAL_STATUS` (`template_generated`) |
| `owner_id` | `_resolve_owner_id(context, fallback_user_id=current_user_id)` |

**The seeded blob**, mirroring what the Zillow path stores so both non-automated create
paths persist the same shape:

```python
{
    "id": None,            # no zpid — the top-level column keeps its FK to
    "url": None,           # zillow.scheduled_listings and stays null too
    "thumbnail": None,
    "price": purchase_price,
    "address": None,       # the hero fills these three in
    "bedrooms": bedrooms,
    "bathrooms": bathrooms,
    "area": None,
    "original_photos": None,
    "lot_size_sqft": None,
    "description": None,
}
```

Written in full rather than as a partial, so the hero has a stable write target — and
because a partial PUT replaces the whole JSONB column anyway (see gap 3 below), the FE is
sending the full object back regardless.

`price` is included because `purchase_price` is mandatory here and the Zillow path keeps it
in the blob too — `build_from_zillow_property` reads it out with `_money_to_decimal` but
only pops `street`/`city`/`state`, so `price` stays.

**Bed/bath are written to both the columns and the blob, and are allowed to diverge
afterwards.** They mean different things: the blob is the property *as found*, the columns
are the property *as underwritten*. An analyst adding a bedroom to the deal moves the
column and should not rewrite history in the blob.

This is safe in both directions. `SaveUnderwritingService._resolve_bedrooms_for_save`
prefers `payload.bedrooms` and only falls back to the blob for rows predating the column,
and `GetUnderwritingService._zillow_from_stored` returns its bed count purely as that same
legacy fallback (`get_underwriting_service.py:562-567`) — consulted only when
`underwriting.bedrooms` is null. Since this path sets the column, the blob value is never
read back as authoritative.

The one rule for the frontend: **read bed/bath from the columns, not the blob.** The blob
is a snapshot, and after the first edit it is deliberately stale.

`market_context` is non-optional on this path — the endpoint always builds one — so
`operating_expenses` and `optimization_list` always seed.

## 4. Service

New `app/iron_bank/services/create_blank_underwriting_service.py`:

```python
context = await self.market_context_reader.build_market_context(
    market_id=market_id, bedrooms=bedrooms, area=None
)
payload = self.builder.build_blank(...)
return await self.save_service.save(payload)
```

Thin on purpose. `CreateUnderwritingFromUrlService` is heavy only because of the duplicate
guard (by URL, then by zpid) and the listing-market guard — none of which have a subject
here.

Reuse the `MarketContextReader` Protocol already defined in
`create_underwriting_from_url_service.py`. It is structural rather than an import because
iron_bank must not import `app/workflows`; that constraint applies identically, so import
the Protocol (intra-domain) and let the router wire `PrepareUwDataJob.from_session(db)` in.

**No duplicate guard, deliberately.** There is no zpid or listing URL to key on, and two
analysts starting blank sheets for the same off-market address is legitimate. Say so in the
class docstring, so its absence does not later read as an oversight.

**Log whether `market_id` and `bedrooms` were supplied** (`logger.info`). Costs nothing and
produces the evidence for the pending product decision on making `bedrooms` mandatory.

## 5. Controller and route

- New `app/iron_bank/controllers/create_blank_underwriting_controller.py` — mirrors
  `CreateUnderwritingFromUrlController` minus the 409/422 handlers it has no errors for.
  Keep `ValueError → 400` and the catch-all logged 500.
- `app/iron_bank/router.py` — add `get_create_blank_underwriting_controller`, wiring
  `SaveUnderwritingService` with `market_service`, `cleaned_data_service` and
  `_opex_by_bedrooms_service(db)` exactly as `get_create_underwriting_from_url_controller`
  does (`router.py:172-192`). That wiring is what lets the save estimate forecasted revenue
  from Airbnb comps — which a blank with both a market and a bedroom count gets for free.
- Route: `POST /underwritings/blank`, `response_model=SaveUnderwritingResult`,
  `status_code=201`, `current_user=Depends(get_current_user)`. Place it next to
  `from-zillow-url` (`router.py:469`).

Auth needs nothing: the global `Depends(get_current_user)` guard in `app/__init__.py`
already covers every route.

---

## What each input combination produces

Verified by running the real builder and context path. All four produce **13 opex rows in
canonical order** — only the amounts differ.

| | market + bedrooms | market, no bedrooms | no market, bedrooms | neither |
| --- | --- | --- | --- | --- |
| opex rows with figures | 10 real | 1 (`MISC 0`) | 10 at `0` | 4 at `0` |
| `details.cleaning_cost` | real | **null** | zeros | zeros |
| `details.property_taxes` | real | **null** | zeros | zeros |
| `purchase_details` | market config + live FRED | defaults + live FRED | defaults + live FRED | defaults + live FRED |
| `taxes.land_assumptions_pct` | market's | `0.2` default | `0.2` default | `0.2` default |
| `taxes` row | full | full | full | full |
| realtors / `bedroom-context` | yes | yes | 404 until market set | 404 until market set |

Internet / Utilities / Pest Control are blank in **all four** — they are sqft-keyed and
`area` is unknown at create. That is now visible rather than silently absent. Nothing
backfills them: `bedroom-context` excludes sqft-keyed rows by design. Accepting an optional
`area` at create would close it, and is the obvious follow-up if it matters.

Note the quirk that *no market, no bedrooms* is better-shaped than *market, no bedrooms*:
the template pass zeroes `cleaning.fee`, `pool_hot_tub.low` and `property_tax_pct`
unconditionally, so it gets four zeroed rows and both `details` blobs populated, while the
scenario that knows more gets one zero and two nulls.

## Known gaps — frontend contract

1. **`realtor_emails` will 422**, not be silently ignored — `UpdateUnderwritingPayload` is
   `extra="forbid"`. Drop the key; realtors already resolve from `market_id` at read time
   via `GetUnderwritingService._populate_realtor_details`.
2. **`lot_size_acres` is read-only.** It is a `@computed_field` derived from
   `lot_size_sqft`, and `StoredZillowProperty` is `extra="allow"` — so writing acres stores
   a dead key and reads back `null`, with no error anywhere. The hero must send
   `lot_size_sqft`.
3. **A partial hero PUT replaces the whole `zillow_property` blob** — it is one JSONB
   column, upserted wholesale. Send the full object that was read, not a patch.
4. **After a market change, merge everything `bedroom-context` returns**: the opex row
   patch (`id: null` means insert), `cleaning_cost`, `property_taxes`, the two
   bedroom-keyed amenity options, **and `land_assumptions_pct` /
   `annual_re_appreciation_pct`** into the `taxes` and `forecasted_revenue` blocks. Those
   last two are the easy miss — they are the only fields on a response named "bedroom
   context" that have nothing to do with bedrooms. They live there because `land_value` and
   `appreciation` are market-level facts stored as columns on `markets.opex_by_bedrooms`,
   so the only way to read them is with a bedroom count in hand.
5. **Sending `taxes` without `optimization_list`** computes `improvement_basis` against an
   empty rehab budget while the stored rows are preserved. The existing
   `require_collections_with_purchase_details` validator guards this shape but fires only
   on `details.purchase_details`, so a taxes-only PUT sails past it. Out of scope here;
   worth extending that validator separately now that a standalone tax save is more likely.

---

## Verification

```bash
uv run pytest tests/iron_bank/ tests/workflows -q
uvicorn main:app --reload
```

`tests/markets/test_market_service_analyst_owner.py` has 8 pre-existing failures on this
branch (`optimization_expense_lift` missing from a `SimpleNamespace` fixture), unrelated to
this work.

**New tests — `tests/iron_bank/test_create_blank_underwriting.py`:**

- All four input combinations, asserting the table above: 13 opex rows in every case, real
  amounts vs zeros vs blanks, and the `cleaning_cost` / `property_taxes` blob states.
- `source == "blank"` persists and round-trips on the detail read.
- `bedrooms` / `bathrooms` / `price` land on the columns **and** in
  `details.zillow_property`, with every other blob key null.
- Changing `bedrooms` via `PUT` moves the column and leaves the blob alone — the snapshot
  is meant to go stale.
- `purchase_details` and `taxes` are both populated, and `interest_rate` is FRED-derived
  (`fred + 0.0035`) rather than the `0.0688` default — the reason the price is mandatory.
- `market_id: 0` folds to `None` rather than 500ing on the FK.
- `owner_id` falls back to the requesting user when the market has no analyst owner.
- `purchase_price` omitted → 422.

**Manual, against a real market:**

1. `POST /iron-bank/underwritings/blank` with `market_id`, `bedrooms`, `bathrooms`,
   `purchase_price` → note the returned id.
2. `GET /iron-bank/underwritings/{id}` → `source: "blank"`, 13 opex rows, populated
   `purchase_details` and `taxes`, and `zillow_property` carrying price/bedrooms/bathrooms
   with null address/area/lot.
3. `GET /iron-bank/underwritings/{id}/bedroom-context?bedrooms=4` → returns the patch. No
   backend change was needed here: it reads `market_id` and `purchase_price` off the stored
   row, not from Zillow data.
4. Repeat step 1 with `market_id` omitted → `market_id: null`, opex rows all at `0`,
   `bedroom-context` 404s until a market is set via `PUT`.
