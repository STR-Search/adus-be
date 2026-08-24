# Cleanup: retiring the Zillow bedroom fallbacks

Follow-up chore for the `underwritings.bedrooms` / `underwritings.bathrooms`
feature. Everything below is **transitional code that exists only because rows
created before those columns have them NULL.** None of it is load-bearing once
`scripts/backfill_underwriting_bedrooms.py` has run in every environment.

## Precondition — do not start until this holds

The backfill must have run on **every** environment (prod included), not just
dev. Verify per environment:

```sql
SELECT source, count(*) AS null_bedrooms
FROM iron_bank.underwritings
WHERE bedrooms IS NULL
GROUP BY source;
```

**Expected: only `legacy_sheet` rows remain.** Those are unresolvable by design —
they were loaded with `is_automated=false`, no stored `zillow_property`, and only
sometimes a matched `zpid` (see `scripts/backfill_legacy_underwritings.py:567`
and `:1100`). In dev that was 741 of 4552 rows.

If any `adus` rows are still NULL, the backfill has not finished — stop and
re-run it rather than deleting the fallbacks.

### The decision this forces

`legacy_sheet` rows will be permanently NULL. Deleting the fallbacks means those
deals get **no furnishing/shipping prices** in the edit context and **no
auto-generated forecasted revenue** — `_opex_by_bedrooms` logs
`iron_bank.get_underwriting.no_bedrooms` and returns `None`.

That is already their behaviour today (they hit `_zillow_from_stored`'s
`(None, None)` early return), so removing the fallbacks costs them nothing. But
confirm nobody has since started relying on those deals rendering prices. If
they have, the answer is to give `legacy_sheet` rows a bedroom count — by hand or
from the sheet — not to keep the fallbacks.

---

## 1. Edit-context fallback

**`app/iron_bank/services/get_underwriting_service.py`** (~lines 73–93, in
`get_edit_context`)

`_zillow_from_listing` and `_zillow_from_stored` each return a 2-tuple whose
second element is *only* the Zillow bedroom count for this fallback. Delete the
fallback and both helpers collapse to returning `zillow_property` alone.

Change the call sites to single assignment:

```python
if underwriting.is_automated is True:
    zillow_property = await self._zillow_from_listing(underwriting)
else:
    zillow_property = await self._zillow_from_stored(underwriting)

opex_by_bedrooms = await self._opex_by_bedrooms(
    underwriting, bedrooms=underwriting.bedrooms
)
```

Then in the two helpers (~lines 421 and 460):

- `_zillow_from_listing` — return `zillow_property`, not `zillow_property, listing.beds`; the two early returns become bare `None`. Drop the "second element is the listing's bed count" paragraph from the docstring.
- `_zillow_from_stored` — return `zillow_property`, not `zillow_property, zillow_property.bedrooms`; same docstring edit.

**Keep** `_opex_by_bedrooms`'s `if bedrooms is None` guard (~line 490). It stops
being about pre-backfill rows and starts being about `legacy_sheet` rows, which
is permanent. Update its comment to say so.

## 2. Update-path fallback

**`app/iron_bank/services/update_underwriting_service.py`**,
`_resolve_bedrooms_for_update` (~lines 166–205)

Delete the last three blocks — the payload `zillow_property`, the stored
`zillow_property`, and the `scheduled_listings` lookup. The method reduces to:

```python
if "bedrooms" in payload.model_fields_set and payload.bedrooms is not None:
    return payload.bedrooms
return existing.bedrooms
```

Drop the "remove it once the backfill has run" line from the docstring.

Watch for a knock-on: with the listing lookup gone, `self.listings_service` may
become unused by this method. It is still used by `_sync_listing_removal` and
`_zillow_property_for_webhook`, so **do not** remove the dependency.

## 3. What NOT to delete

These look similar but are permanent. Leaving them is correct.

| Location | Why it stays |
|---|---|
| `save_underwriting_service.py` `_resolve_bedrooms_for_save` / `_resolve_bathrooms_for_save` Zillow chains | At creation there is no stored column yet — the row does not exist. These are the documented backstop for direct `POST /iron-bank/underwritings` callers that omit both fields, guaranteeing the invariant on every entry path. Not a rollout artifact. |
| `save_underwriting_service.py` `_listing_for_save` | Shared by both save resolvers above. |
| `_opex_by_bedrooms`'s `bedrooms is None` guard | Becomes the `legacy_sheet` guard (see §1). |
| `prepare_uw_data_job.py` `run` / `build_market_context` using `listing.beds` | Pre-creation: no underwriting row exists yet. Zillow seeds the column once; this is by design, not a fallback. |
| `details.zillow_property.bedrooms` / `.bathrooms` | Zillow's original observation, kept deliberately alongside the analyst's assumption. Never delete. |

## 4. Tests to delete or retarget

- `tests/iron_bank/test_get_underwriting_service.py:607` — `test_edit_context_falls_back_to_zillow_when_the_column_is_null`. **Delete.** Consider replacing with one asserting a NULL-bedrooms row yields `opex_by_bedrooms is None` and still hydrates `zillow_property`.
- `tests/iron_bank/test_update_underwriting_service.py:337` — `test_update_estimates_revenue_for_automated_beds_from_scheduled_listings`. **Delete** (exercises the removed listing lookup).
- `tests/iron_bank/test_update_underwriting_service.py:365` — `test_update_estimates_revenue_for_non_automated_beds_from_stored_zillow`. **Delete** (exercises the removed stored-blob branch).
- `tests/iron_bank/test_update_underwriting_service.py:396` — `test_update_skips_revenue_when_no_bedrooms_source`. **Keep**, but simplify: the fixture no longer needs `zpid`/`detail`, just `bedrooms=None`.
- `tests/iron_bank/test_update_underwriting_service.py:991` — comment says "Zillow is only consulted for rows predating the column". Update.
- **Keep** `test_update_prefers_the_payload_bedrooms_over_everything_stored` and `test_update_uses_the_stored_column_when_the_payload_omits_bedrooms` — they cover the surviving precedence. Their fixtures carry a stored `zillow_property` purely to prove it *loses*; that assertion still has value.

## 5. Optional

`scripts/backfill_underwriting_bedrooms.py` becomes dead once run everywhere.
Keeping it is harmless and it is idempotent (re-running reports zero updates), so
it doubles as a repair tool if rows are ever imported with NULL columns. No need
to delete.

---

## Unrelated find, worth doing separately

`prepare_uw_data_job.py` `_purchase_price_of` falls back from
`underwritings.purchase_price` to `detail.purchase_details["purchase_price"]`.
As of the dev check, **zero rows** need that fallback:

```sql
SELECT count(*) FROM iron_bank.underwritings u
JOIN iron_bank.uw_details d ON d.underwriting_id = u.id
WHERE u.purchase_price IS NULL
  AND d.purchase_details ->> 'purchase_price' IS NOT NULL;
-- dev: 0
```

The column is promoted from the blob on every save/update carrying purchase
details, so the fallback may be unreachable. Re-run that query against prod
before deleting it — it is cheap insurance, so removing it is optional and
independent of the backfill.

## Also still open (not cleanup)

- **FE merge logic** for `GET /iron-bank/underwritings/{id}/bedroom-context` — the response is deliberately narrow, and the FE must *merge*, not replace: the sqft-keyed opex rows (`internet`, `pest_control`, `utilities`), the "Design / Project Management" item, and the market's must-have amenities are absent from the response and must survive untouched.
- **`get_prepare_uw_data`'s error mapping** (`prepare_uw_data_controller.py:20`) still maps bare `ValueError` to 404. Since `pydantic.ValidationError` subclasses `ValueError`, a malformed prepared payload returns 404 with a pydantic dump instead of a 500. Fix mirrors `BedroomContextNotFoundError`: a dedicated `ListingNotFoundError` in `prepare_uw_data_job.py`. Left alone because it changes an existing endpoint's status codes and the FE may branch on that 404.
