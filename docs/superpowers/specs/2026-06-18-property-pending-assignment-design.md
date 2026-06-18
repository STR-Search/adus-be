# Property Pending Assignment Design

## Goal

Populate `Underwriting.property_pending` during underwriting creation from the
corresponding `ScheduledListing.home_status`.

## Behavior

`property_pending` is `false` when `home_status` is `NULL` or `FOR_SALE`. It is
`true` for every other status, including the currently observed values `SOLD`,
`OTHER`, `RECENTLY_SOLD`, and `PENDING`.

## Design

`SaveUnderwritingService` will assign listing-derived boolean fields through a
dedicated helper. During `save()`, the service will load the scheduled listing
using the payload's `zpid`, then invoke the helper with `underwriting_data` and
the listing. The helper will set `property_pending` according to the rule above.

This logic will remain separate from `_apply_calculated_underwriting_fields()`,
because `property_pending` is a direct classification from listing data rather
than a calculated financial field.

The existing validation behavior for missing `zpid` or missing listings will
not be broadened beyond what the save flow already requires for automated
underwriting revenue calculation.

## Tests

Service tests will verify that persisted `underwriting_data` receives:

- `property_pending = false` for `NULL` and `FOR_SALE`.
- `property_pending = true` for `SOLD`, `OTHER`, `RECENTLY_SOLD`, and `PENDING`.

The implementation will follow a red-green cycle: add the expectations first,
confirm they fail because the field is absent, then add the dedicated helper.
