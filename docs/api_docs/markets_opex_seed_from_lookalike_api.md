# Seed Opex From a Lookalike Market API

This endpoint copies a market's operating-expense rows onto an **exploratory** market, so a new market can start from the numbers of an established one instead of being filled in from scratch.

The copy is a **one-time snapshot, not a live link**. Once seeded, the rows belong to the target market and are edited through the ordinary opex endpoints. Later changes to the source market do not flow through.

## Environment

Set the ADUS backend base URL in your service:

```env
ADUS_BE_BASE_URL=https://adus-be.onrender.com
```

For local testing this may be:

```env
ADUS_BE_BASE_URL=http://localhost:8000
```

## Authentication

Every route on this backend is authenticated. Send your API key in the `X-ADUS-API-KEY` header:

```http
X-ADUS-API-KEY: <your key>
```

Ask the ADUS team to issue you a key. Keys are stored hashed on our side, so the plaintext is shown **once at creation and never again** — store it in your secret manager at that moment. If it is lost, we issue a new one and revoke the old.

Two notes that save debugging time:

- If the `X-ADUS-API-KEY` header is **missing or empty**, the request does not fail as "no API key". The backend falls through to its other credential type (a browser session token) and you get `401 {"detail": "Missing Authorization header"}`. That message means *no credential arrived at all* — check that your HTTP client is actually attaching the header.
- If the header is present but the key is wrong or revoked, you get `401 {"detail": "Invalid API key"}`.

## Endpoint

```http
POST {ADUS_BE_BASE_URL}/markets/{market_id}/opex/seed-from-lookalike
```

| Part | Description |
|---|---|
| `market_id` (path) | The **target**: the exploratory market receiving the rows. |
| `source_market_id` (body) | The **source**: the lookalike market the rows are copied from. |

### Request Body

```json
{
  "source_market_id": 7
}
```

`source_market_id` is required and must be an integer. Both sides are numeric market IDs, not slugs.

<!-- ### Finding market IDs

`GET /markets/` lists markets and accepts a `market_status` filter, which is the quickest way to get both sides of the call:

```bash
# candidate targets
curl -H "X-ADUS-API-KEY: ${ADUS_API_KEY}" \
  "${ADUS_BE_BASE_URL}/markets/?market_status=exploratory&page_size=100"

# candidate sources
curl -H "X-ADUS-API-KEY: ${ADUS_API_KEY}" \
  "${ADUS_BE_BASE_URL}/markets/?market_status=active&page_size=100"
``` -->

## What Gets Copied

Two tables are seeded together, in one transaction:

| Table | Keyed by | Typical row count |
|---|---|---|
| `opex_by_bedrooms` | bedroom count | 7 |
| `opex_by_size` | square-foot band | 6 |

Those counts are the convention, **not a guarantee** — the endpoint copies however many rows the source actually has, and the response tells you what it wrote. Every expense column on each row is carried across unchanged; only the database identity of each row is new.

Because both tables are written under a single commit, a market is never left with one table seeded and the other empty. If either insert fails, neither lands.

## Preconditions

All four are checked **before anything is written**, so a rejected call leaves the target exactly as it was.

1. The target market must exist, and its status must be `exploratory`.
2. The source market must exist.
3. The source must have rows in **both** opex tables.
4. The target must have **no** rows in either opex table.
5. Source and target must be different markets.

## Example Call

```bash
curl -X POST "${ADUS_BE_BASE_URL}/markets/42/opex/seed-from-lookalike" \
  -H "X-ADUS-API-KEY: ${ADUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"source_market_id": 7}'
```

## Successful Response

HTTP `201`:

```json
{
  "target_market_id": 42,
  "source_market_id": 7,
  "bedrooms_created": 7,
  "size_created": 6
}
```

`bedrooms_created` and `size_created` are the actual number of rows written to each table. Check them rather than assuming 7 and 6.

To read the seeded rows back:

```bash
curl -H "X-ADUS-API-KEY: ${ADUS_API_KEY}" \
  "${ADUS_BE_BASE_URL}/opex/bedrooms/?market_id=42"

curl -H "X-ADUS-API-KEY: ${ADUS_API_KEY}" \
  "${ADUS_BE_BASE_URL}/opex/size/?market_id=42"
```

## Error Responses

Note that `detail` is a **plain string** on some errors and an **object** on others. Handle both shapes.

### 409 — Target already has opex rows

The most common one you will hit, and it is the expected answer to a repeat call.

```json
{
  "detail": {
    "message": "Rows are already there for this market in opex_by_bedrooms, opex_by_size, go ahead and edit them if needed.",
    "tables": ["opex_by_bedrooms", "opex_by_size"]
  }
}
```

`tables` names which tables were already populated. Rows in **either** table refuse the whole seed — we do not partially fill the other one, because that would mix two different sources into one market.

This is a refusal, not a failure: the market already has its numbers, and they are edited through `PATCH /opex/bedrooms/{record_id}` and `PATCH /opex/size/{record_id}`. **There is no overwrite or force flag.** If a market genuinely needs re-seeding from a different source, ask the ADUS team — its existing rows have to be cleared first, and that is deliberately a manual decision since an analyst may have already tuned them.

### 409 — Target is not exploratory

```json
{
  "detail": {
    "message": "Market 42 has status 'active'; opex can only be seeded into an exploratory market",
    "market_status": "active"
  }
}
```

Seeding is only for markets still being explored. An active market's expenses are real numbers in use downstream, so the endpoint will not write over them.

### 400 — Source has nothing to copy

```json
{
  "detail": {
    "message": "Lookalike market 7 has no rows in opex_by_size; nothing to seed from",
    "empty_tables": ["opex_by_size"]
  }
}
```

`empty_tables` lists the tables that came back empty. Pick a different, fully populated source market. A source missing one table is rejected outright rather than half-copied.

### 400 — Source and target are the same market

```json
{
  "detail": "Market 42 cannot be seeded from itself"
}
```

### 404 — Market not found

```json
{
  "detail": "market_id 7 not found"
}
```

Raised for either side. The message names the ID that could not be resolved, so you can tell which one was wrong. Soft-deleted markets also report as not found.

### 422 — Malformed body

Standard FastAPI validation error, returned when `source_market_id` is missing or is not an integer:

```json
{
  "detail": [
    {
      "type": "int_parsing",
      "loc": ["body", "source_market_id"],
      "msg": "Input should be a valid integer, unable to parse string as an integer",
      "input": "abc"
    }
  ]
}
```

### 401 — Authentication failed

```json
{ "detail": "Invalid API key" }
```

or, when no credential arrived at all:

```json
{ "detail": "Missing Authorization header" }
```

See the Authentication section above.

### 500 — Unexpected failure

```json
{
  "detail": "Failed to seed opex from lookalike market"
}
```

Nothing was written — the transaction is rolled back. Safe to retry. If it persists, contact the ADUS team with the target and source IDs and the approximate timestamp.

## Retries and Concurrency

The endpoint is safe to retry: a second successful call for the same target returns `409` with the "rows are already there" message rather than duplicating anything.

Do **not** fire concurrent seed calls for the same target market. The precondition checks are not a lock, and two simultaneous calls can both pass them; one will then fail on a database constraint and return `500`. Serialize per target market.

<!-- ## Interactive Reference

The live OpenAPI docs are at `{ADUS_BE_BASE_URL}/docs`. Click **Authorize** and paste your key into the `X-ADUS-API-KEY` field to try calls from the browser. -->
