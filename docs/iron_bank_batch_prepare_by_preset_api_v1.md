# Iron Bank Batch Underwriting by Preset API (v1)

This endpoint lets an external team trigger our batch underwriting job for a single
Zillow scheduled **preset** — for example, right after a scheduled preset run completes.

## Authentication

Every request must include your API key in the **`X-ADUS-API-KEY`** header. This is the
only credential you need — there is no token exchange, login flow, or expiry to manage.

```http
X-ADUS-API-KEY: adus_sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

- Keep the key secret — treat it like a password. Anyone with it can call the API as you.
- If a key is leaked, tell us and we will revoke it and issue a new one.
- A request with a missing or invalid key returns HTTP `401`.

## Environment

Set the ADUS backend base URL and your key in your service. The URL is as below for now,
but will change when we point a real domain at it:

```env
ADUS_BE_BASE_URL=https://adus-be.onrender.com
ADUS_API_KEY=adus_sk_your_key_here
```

For local testing this may be:

```env
ADUS_BE_BASE_URL=http://localhost:8000
```

## Endpoint

```http
POST {ADUS_BE_BASE_URL}/iron-bank/underwritings/batch-prepare-by-preset
```

## Query Parameters

| Parameter | Required | Description |
|---|---:|---|
| `preset_id` | Yes | The scheduled preset UUID (`zillow.scheduled_presets.id`). |
| `since_hours` | Yes | Only process active scheduled listings created within the last N hours. Must be `>= 1`. |
| `limit` | No | Optional cap on how many matching listings to process. Must be `>= 1` when provided. |

The job finds listings directly by `scheduled_listings.preset_id` for the given preset. It
only processes listings where `keep_updated = true`, `remove_listing = false`, and
`created_at` is inside the `since_hours` window.

## Example Call

```bash
curl -X POST \
  "${ADUS_BE_BASE_URL}/iron-bank/underwritings/batch-prepare-by-preset?preset_id=3f8b0c1e-1a2b-4c3d-9e8f-abc123456789&since_hours=2&limit=50" \
  -H "X-ADUS-API-KEY: ${ADUS_API_KEY}"
```

To process all matching listings in the time window, omit `limit`:

```bash
curl -X POST \
  "${ADUS_BE_BASE_URL}/iron-bank/underwritings/batch-prepare-by-preset?preset_id=3f8b0c1e-1a2b-4c3d-9e8f-abc123456789&since_hours=2" \
  -H "X-ADUS-API-KEY: ${ADUS_API_KEY}"
```

## Successful Response

With valid parameters, the API returns a summary of what was found and processed:

```json
{
  "preset_id": "3f8b0c1e-1a2b-4c3d-9e8f-abc123456789",
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

## Error Responses

| HTTP | Body | Meaning |
|---:|---|---|
| `401` | `{"detail": "Invalid API key"}` | Missing or invalid `X-ADUS-API-KEY` header. |
| `422` | validation error | A query parameter is missing or malformed (e.g. `preset_id` is not a UUID, `since_hours < 1`). |
| `500` | `{"detail": "Failed to prepare and save underwritings for preset"}` | The job failed. Safe to retry; already-saved underwritings are skipped as `skipped_existing`. |

## Sample Client

A runnable Python client is provided alongside this doc at
[`examples/batch-prepare-by-preset/`](../examples/batch-prepare-by-preset/). It reads the
base URL and key from a `.env` file and calls the endpoint — see its `README.md`.
