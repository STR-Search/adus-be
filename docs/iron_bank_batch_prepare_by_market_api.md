# Iron Bank Batch Underwriting by Market API

This endpoint lets the Zillow scheduling team trigger our batch underwriting job after a successful scheduled preset run for a market.

## Environment

Set the ADUS backend base URL in your service. The URL is as below for now, but will change when we set a valid domain to point towards it:

```env
ADUS_BE_BASE_URL=https://adus-be.onrender.com
```

For local testing this may be:

```env
ADUS_BE_BASE_URL=http://localhost:8000
```

## Endpoint

```http
POST {ADUS_BE_BASE_URL}/iron-bank/underwritings/batch-prepare-by-market
```

**There is currently no authentication on this endpoint. This is for test/integration purposes only.**

## Query Parameters

| Parameter | Required | Description |
|---|---:|---|
| `market_id` | Yes | Market ID from `scheduled_presets.market_id`. |
| `since_hours` | Yes | Only process active scheduled listings created within the last N hours. Must be `>= 1`. |
| `limit` | No | Optional cap on how many matching listings to process. Must be `>= 1` when provided. |

The job finds listings by joining `zillow.scheduled_listings` to `scheduled_presets` for the given market. It only processes listings where `keep_updated = true`, `remove_listing = false`, and `created_at` is inside the `since_hours` window.

**One integration detail to align on**: this endpoint runs by `market_id`, not by preset. If a market has multiple scheduled presets, we should think through the orchestration together so the batch underwriting trigger happens after the relevant preset runs for that market have completed. That way, the market-level job sees the full set of newly updated listings we expect it to process.

## Example Call

```bash
curl -X POST "${ADUS_BE_BASE_URL}/iron-bank/underwritings/batch-prepare-by-market?market_id=12&since_hours=2&limit=50"
```

If you want to process all matching listings in the time window, omit `limit`:

```bash
curl -X POST "${ADUS_BE_BASE_URL}/iron-bank/underwritings/batch-prepare-by-market?market_id=12&since_hours=2"
```

## Successful Response

With valid parameters, the API returns a summary of what was found and processed:

```json
{
  "market_id": 12,
  "found": 3,
  "processed": 3,
  "saved": 1,
  "skipped_existing": 1,
  "skipped_no_purchase_price": 1,
  "failed": 0,
  "results": [
    {
      "zpid": "12345678",
      "status": "saved",
      "underwriting_id": 101
    },
    {
      "zpid": "23456789",
      "status": "skipped_existing",
      "underwriting_id": 99
    },
    {
      "zpid": "34567890",
      "status": "skipped_no_purchase_price"
    }
  ]
}
```

Per-listing statuses can be:

- `saved`: a new draft underwriting was created.
- `skipped_existing`: an underwriting already exists for that Zillow property.
- `skipped_no_purchase_price`: the listing could not produce a purchase price.
- `failed`: processing that listing raised an error; the response item includes `error`.

If the endpoint itself fails, it returns HTTP `500` with:

```json
{
  "detail": "Failed to prepare and save underwritings for market"
}
```