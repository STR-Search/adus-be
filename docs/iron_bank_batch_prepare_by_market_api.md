# Iron Bank Batch Underwriting by Market API

This endpoint lets the Zillow scheduling team submit a batch underwriting job for a
market. The request returns immediately with a job ID. The caller then polls the job
endpoint until processing succeeds or fails.

## Authentication

Every request must include an API key in the **`X-ADUS-API-KEY`** header. The key is
required when submitting the job and when polling its status.

```http
X-ADUS-API-KEY: adus_sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

- Keep the key secret and treat it like a password.
- If a key is leaked, tell us so it can be revoked and replaced.
- A missing or invalid key returns HTTP `401`.

## Environment

Set the ADUS backend base URL and API key in your service:

```env
ADUS_BE_BASE_URL=https://adus-be.onrender.com
ADUS_API_KEY=adus_sk_your_key_here
```

For local testing:

```env
ADUS_BE_BASE_URL=http://localhost:8000
```

## Flow

1. Submit the market and listing-selection parameters to the batch endpoint.
2. Receive HTTP `202 Accepted` with a job ID and `queued` status.
3. Poll `GET /iron-bank/jobs/{job_id}` with the same API key.
4. Stop polling when the status is `succeeded` or `failed`.
5. For a succeeded job, read the batch summary from `result`. For a failed job,
   inspect `error`.

Job statuses are:

- `queued`: accepted and waiting to start.
- `running`: processing is in progress.
- `succeeded`: processing finished; `result` contains the batch summary.
- `failed`: the job could not finish; `error` contains the failure message.

## Submit a Job

```http
POST {ADUS_BE_BASE_URL}/iron-bank/underwritings/batch-prepare-by-market
```

### Query Parameters

| Parameter | Required | Description |
|---|---:|---|
| `market_id` | Yes | Market ID from `scheduled_presets.market_id`. |
| `since_hours` | Yes | Only process active scheduled listings created within the last N hours. Must be `>= 1`. |
| `limit` | No | Optional cap on matching listings. Must be `>= 1` when provided. |

The job finds listings by joining `zillow.scheduled_listings` to
`zillow.scheduled_presets` for the supplied market. It only processes listings where
`keep_updated = true`, `remove_listing = false`, and `created_at` is inside the
`since_hours` window.

This endpoint operates at market level. If a market has multiple scheduled presets,
submit the market job after the relevant preset runs have completed so it sees the full
set of newly updated listings.

### Example

```bash
curl -X POST \
  "${ADUS_BE_BASE_URL}/iron-bank/underwritings/batch-prepare-by-market?market_id=12&since_hours=2&limit=50" \
  -H "X-ADUS-API-KEY: ${ADUS_API_KEY}"
```

Omit `limit` to process every matching listing in the time window:

```bash
curl -X POST \
  "${ADUS_BE_BASE_URL}/iron-bank/underwritings/batch-prepare-by-market?market_id=12&since_hours=2" \
  -H "X-ADUS-API-KEY: ${ADUS_API_KEY}"
```

### Accepted Response

The API returns HTTP `202 Accepted` after persisting the job:

```json
{
  "id": "7af61df0-1ec1-42f8-a334-df5a3d50cc79",
  "status": "queued"
}
```

Save `id`; it is required to retrieve the outcome.

## Poll a Job

```http
GET {ADUS_BE_BASE_URL}/iron-bank/jobs/{job_id}
```

### Example

```bash
curl \
  "${ADUS_BE_BASE_URL}/iron-bank/jobs/7af61df0-1ec1-42f8-a334-df5a3d50cc79" \
  -H "X-ADUS-API-KEY: ${ADUS_API_KEY}"
```

While processing, the response resembles:

```json
{
  "id": "7af61df0-1ec1-42f8-a334-df5a3d50cc79",
  "job_type": "batch_prepare_by_market",
  "status": "running",
  "params": {
    "market_id": 12,
    "since_hours": 2,
    "limit": 50
  },
  "result": null,
  "error": null,
  "created_at": "2026-07-13T12:00:00Z",
  "started_at": "2026-07-13T12:00:01Z",
  "finished_at": null
}
```

Poll at a reasonable interval, such as every 2-5 seconds. Do not submit the same job
again merely because it is still `queued` or `running`.

### Successful Job

When `status` is `succeeded`, `result` contains the completed batch summary:

```json
{
  "id": "7af61df0-1ec1-42f8-a334-df5a3d50cc79",
  "job_type": "batch_prepare_by_market",
  "status": "succeeded",
  "params": {
    "market_id": 12,
    "since_hours": 2,
    "limit": 50
  },
  "result": {
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
  },
  "error": null,
  "created_at": "2026-07-13T12:00:00Z",
  "started_at": "2026-07-13T12:00:01Z",
  "finished_at": "2026-07-13T12:00:24Z"
}
```

Per-listing statuses inside `result.results` can be:

- `saved`: a new draft underwriting was created.
- `skipped_existing`: an underwriting already exists for that Zillow property.
- `skipped_no_purchase_price`: the listing could not produce a purchase price.
- `failed`: processing that listing raised an error; the item includes `error`.

A job can have `status: "succeeded"` while individual listings have
`status: "failed"`. In that case, the batch completed and its `failed` count reports
the per-listing failures.

### Failed Job

If the batch cannot complete, the polling response has `status: "failed"`, a null
`result`, and an error message:

```json
{
  "id": "7af61df0-1ec1-42f8-a334-df5a3d50cc79",
  "job_type": "batch_prepare_by_market",
  "status": "failed",
  "params": {
    "market_id": 12,
    "since_hours": 2,
    "limit": 50
  },
  "result": null,
  "error": "Failure message",
  "created_at": "2026-07-13T12:00:00Z",
  "started_at": "2026-07-13T12:00:01Z",
  "finished_at": "2026-07-13T12:00:02Z"
}
```

## HTTP Error Responses

| HTTP | Applies to | Meaning |
|---:|---|---|
| `401` | Submit and poll | Missing or invalid `X-ADUS-API-KEY` header. |
| `404` | Poll | No job exists for the supplied job ID. |
| `422` | Submit and poll | A path or query parameter is missing or malformed. |
| `500` | Submit | The request could not be accepted or persisted. No job ID is returned. |

Background processing errors do not change the polling endpoint's HTTP status. A
successfully retrieved job still returns HTTP `200`; inspect its `status` and `error`
fields to determine whether execution failed.

## Legacy Contract

The previous synchronous contract is preserved in
[`iron_bank_batch_prepare_by_market_api_v1.md`](iron_bank_batch_prepare_by_market_api_v1.md).
