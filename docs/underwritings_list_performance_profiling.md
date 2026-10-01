# Underwritings List API: Performance Profiling

**Endpoint:** `GET /iron-bank/underwritings`
**Branch:** `feat/profiling`
**Date:** 2026-09-25 → 2026-09-26

## TL;DR

- The endpoint took **~2.9 s locally** and **~10.5 s on Render**. Profiling shows
  **~97% of that time is waiting on network round trips to the database**. The
  actual work (SQL execution, Python, serialization) is **~65 ms**.
- The DB is in **Mumbai (`ap-south-1`)**. The Render service is in **Ohio
  (`us-east-2`)**. Every query crosses the Ohio ↔ Mumbai link, and a request
  runs ~15 of them one after another.
- Two code fixes are in: **batching the markets lookup** (−719 ms locally) and a
  **process-level cache for `reference.enum_options`** (−124 ms locally).
  Together they took local p50 from **2949 → 2093 ms (−29%)**.
- **Next code fix:** `joinedload` for the two one-to-one relations
  (`detail`, `taxes`) removes 2 more queries: ~−240 ms locally, ~−1.3 s on Render.
- **Moving the DB to Ohio, next to Render,** is the biggest single lever:
  projected **~10.2 s → ~120–250 ms** server time, about **40× faster**, with no
  further code changes.

---

## 1. How we profiled

### Instrumentation (`app/core/profiling.py`, behind `PROFILING_ENABLED`)

| Piece | What it does |
|---|---|
| `ProfilingMiddleware` | Pure ASGI middleware. Creates a per-request profile in a `ContextVar`, emits one `request.profile` log line per request, and sets a `Server-Timing` response header |
| `timed("name")` | Span helper placed at each step (auth, repository, service, enrichment). A no-op when profiling is off |
| SQLAlchemy engine hooks | Time **every** SQL statement (`before/after_cursor_execute`), plus the pool's pre-ping and new physical connections. These are round trips no query-level log would show |

Spans in the request path:

```
auth                                   get_current_user (API key → user)
controller.get_underwritings           everything the endpoint does to build the result
├── repo.count                         SELECT count(*) over the filtered set
├── repo.page_with_children            page query + 5 selectinloads
├── service.to_result                  ORM → Pydantic (CPU only)
├── service.hydrate_zillow             listings + listing details for automated rows
├── enrich.reference_labels            tag slug → label
├── enrich.user_refs                   analyst / approver / owner
└── enrich.realtor_details             markets → realtors
other                                  FastAPI validation + JSON serialization
```

`server.db` is the summed time of all SQL statements (send → rows received).
`db-ping` and `db-connect` are tracked separately.

### Tools

- `scripts/bench_endpoint.py`: runs N requests (2 warm-up requests discarded)
  and reports p50/p95/max of the client total plus every `Server-Timing` entry.
- `scripts/db_rtt.py`: measures the round trip to the DB from wherever it runs.

All benchmark runs below are **p50 over n=20**, default filters,
`page_size=25`, API-key auth.

---

## 2. Where the time goes

### Network measurements from BD (local machine)

| Measurement | Value |
|---|---|
| Raw network round trip to the Mumbai pooler (TCP connect) | **~40 ms** |
| One SQL query through the app's engine (`SELECT 1`) | **~119 ms** (≈ 3 network round trips at the protocol level) |
| `pool_pre_ping` on connection checkout | **~195 ms** |
| Opening a new DB connection (TCP + TLS + auth) | **~900 ms** (only on a cold pool) |

So every query costs ~120 ms locally, whatever it does. A request that runs
~15 queries pays ~1.8 s before any real work happens.

### Round trips in one request

| Step | Where | Queries |
|---|---|---|
| Pre-ping on checkout | `app/core/database.py` | (ping) |
| API key → user | `app/users/services/api_key_service.py` | 2 |
| Count | `underwriting_repository.py` (`get_all_paginated`) | 1 |
| Page + 5 `selectinload`s (detail, taxes, optimization_items, operating_expenses, comp_set) | `underwriting_repository.py` | 6 |
| Zillow listings + listing details | `get_underwriting_service.py` (`_hydrate_automated_zillow`) | 2 |
| Reference labels | `_populate_reference_labels` | 1 → **0 (cached)** |
| User refs | `_populate_user_refs` | 1 |
| Markets + realtors | `_populate_realtor_details` | **N + 1 → 2 (batched)** |

The queries run strictly one after another. One `AsyncSession` uses one
connection, and a Postgres connection runs one statement at a time.

---

## 3. What we implemented

### 3.1 Batched markets lookup (removed an N+1)

`_populate_realtor_details` called `market_repository.get_by_id` in a loop, once
per distinct market on the page (~7 on a 25-row page). It was replaced with a
single `MarketRepository.get_by_ids`, the same pattern as
`RealtorRepository.get_by_ids`.

**Result:** `enrich.realtor_details` went from **966.5 → 247.3 ms** (8 queries → 2).

### 3.2 Process-level cache for `reference.enum_options`

`ReferenceDataService` already had a cache, but the service is constructed per
request, so the cache never outlived a request. It is now a module-level TTL
cache shared across requests:
- It stores immutable snapshots, not ORM objects.
- It is cleared on `create_option` / `update_option`.
- `validate_active_option` stays on fresh per-request data, so the write path
  stays strict.

**Result:** `enrich.reference_labels` went from **124.1 → 0.2 ms**.

**Known trade-off:** with several app instances, a create/update only clears the
cache on the instance that handled it. The other instances serve stale labels
for up to the TTL. Cross-instance invalidation (e.g. Redis pub/sub) is a later
follow-up.

### 3.3 Before / after (local, BD → Mumbai DB)

| Metric (p50, ms) | Baseline | After markets batch | After enum cache | Δ total |
|---|---|---|---|---|
| `auth` | 439.5 | 444.5 | 433.5 | – |
| `repo.count` | 122.2 | 123.5 | 121.7 | – |
| `repo.page_with_children` | 834.6 | 848.5 | 839.2 | – |
| `service.to_result` | 5.3 | 5.1 | 6.0 | – |
| `service.hydrate_zillow` | 324.1 | 339.9 | 316.2 | – |
| `enrich.reference_labels` | 121.2 | 124.1 | **0.2** | **−121** |
| `enrich.user_refs` | 119.6 | 121.7 | 119.5 | – |
| `enrich.realtor_details` | 966.5 | **247.3** | 243.7 | **−723** |
| `controller.get_underwritings` | 2498.6 | 1820.0 | 1647.4 | −851 |
| `db` (all SQL) | 2699.2 | 2002.4 | 1835.1 | −864 |
| `db-ping` | 198.2 | 199.7 | 194.7 | – |
| `other` (validation + serialization) | 11.3 | 11.0 | 11.3 | – |
| **`server.total`** | **2948.7** | **2275.8** | **2092.9** | **−856 (−29%)** |
| `client_total_ms` | 2950.7 | 2277.5 | 2094.6 | −856 |
| Response size | 292.2 KiB | 292.1 KiB | 316.3 KiB | |

Spans that the fixes didn't touch stayed within noise, which confirms each fix
only affected the step it targeted. The `auth + controller + other` spans add up
to `server.total`: 433.5 + 1647.4 + 11.3 = 2092.2 ≈ 2092.9.

The response grew between the last two runs (292 → 316 KiB) for the same
25-row page. This is most likely data changes between runs. It should be
confirmed by diffing one response from each.

---

## 4. Render (Ohio) vs local

### Request path

```
Local:   you (BD) ── laptop ──┬── Mumbai DB ──┐    ~45 round trips × ~40 ms
                              └───────────────┘

Render:  you (BD) ─────► Ohio ──┬── Mumbai DB ──┐  ~45 round trips × ~214 ms   ◄ the problem
                                └───────────────┘
         you (BD) ◄───── Ohio                      once, with the response
```

The BD ↔ Ohio leg is paid **once** per request. The Ohio ↔ Mumbai leg is paid
**~45 times**.

### Render benchmark (both fixes deployed)

| Metric (p50, ms) | Local | Render (Ohio) | Ratio |
|---|---|---|---|
| `auth` | 433.5 | 2349.8 | 5.4× |
| `repo.count` (1 query) | 121.7 | **643.0** | 5.3× |
| `repo.page_with_children` | 839.2 | 3881.7 | 4.6× |
| `service.hydrate_zillow` | 316.2 | 1298.7 | 4.1× |
| `enrich.reference_labels` | 0.2 | 0.1 | – |
| `enrich.user_refs` (1 query) | 119.5 | **641.0** | 5.4× |
| `enrich.realtor_details` (2 queries) | 243.7 | 1285.2 | 5.3× |
| `db` (all SQL) | 1835.1 | 9009.4 | 4.9× |
| `db-ping` | 194.7 | 1066.0 | 5.5× |
| `other` | 11.3 | 11.8 | – |
| **`server.total`** | **2092.9** | **10151.3** | **4.9×** |
| **`client_total_ms`** | **2094.6** | **10528.9** | |

**Reading it:**
- Single-query spans cost **~640 ms** on Render vs ~120 ms locally. At ~3 network
  round trips per query, that's **~214 ms per round trip**, the normal Ohio ↔ Mumbai
  latency. Nothing else is wrong on Render.
- `client_total − server.total` ≈ **380 ms**. That is the entire cost of you being
  in BD and the server in Ohio: ~4% of the request.
- `other` and `to_result` are the same in both places. CPU work isn't a factor.

---

## 5. Next code-side fix: `joinedload` for `detail` and `taxes` (−2 queries)

`get_all_paginated` currently loads all five relationships with `selectinload`.
Each one is a separate query after the page query:

```sql
SELECT ... FROM iron_bank.underwritings WHERE ... ORDER BY ... LIMIT 25;       -- 1
SELECT ... FROM iron_bank.uw_details  WHERE underwriting_id IN (...);          -- 2
SELECT ... FROM iron_bank.uw_taxes    WHERE underwriting_id IN (...);          -- 3
SELECT ... FROM iron_bank.uw_optimization_items WHERE underwriting_id IN (...);-- 4
SELECT ... FROM iron_bank.uw_operating_expenses WHERE underwriting_id IN (...);-- 5
SELECT ... FROM iron_bank.uw_comp_set WHERE underwriting_id IN (...);          -- 6
```

- **`detail` and `taxes` are one-to-one** (`uselist=False`), and the DB enforces it
  with unique indexes `uq_uw_details_underwriting_id` and
  `uq_uw_taxes_underwriting_id`. A `LEFT OUTER JOIN` can't duplicate parent rows,
  so `LIMIT 25` still means 25 underwritings. They can be folded into query 1
  with `joinedload`.
- **The three collections stay on `selectinload`.** Joining several one-to-many
  collections multiplies rows (10 items × 12 expenses × 8 comps = 960 rows per
  deal).
- The response doesn't change. The same bytes travel, just in one result set
  instead of three.

**Projected saving:**

| | Today | With `joinedload` |
|---|---|---|
| Queries in `repo.page_with_children` | 6 | 4 |
| Local `server.total` | ~2093 ms | **~1850 ms** (−~240) |
| Render `server.total` (DB in Mumbai) | ~10,151 ms | **~8,870 ms** (−~1,280) |

### Further code-side options (backlog)

| Option | ≈ Saving (local) | Notes |
|---|---|---|
| Lean list response: drop the 3 collections and Zillow hydration from the list | ~700 ms + most of the payload | Needs confirmation of which fields the frontend list view renders |
| Single joined query for API key → user | ~120 ms | Only helps API-key callers; browser (Clerk) users already do 1 lookup |
| `count(*) OVER ()` in the page query | ~120 ms | Parked: an empty page past the end carries no count and needs a fallback query |

---

## 6. Projection: moving the DB to Ohio (`us-east-2`)

Each Render span is almost exactly *round trips × 214 ms*. What's left over is
the real work:

| Span (Render) | ms | ≈ Round trips at 214 ms | Remainder (real work) |
|---|---|---|---|
| `auth` (ping + 2 queries) | 2350 | 11 | ~0 |
| `repo.count` | 643 | 3 | ~1 |
| `repo.page_with_children` | 3882 | 18 | ~30 |
| `service.hydrate_zillow` | 1299 | 6 | ~15 |
| `enrich.user_refs` | 641 | 3 | ~0 |
| `enrich.realtor_details` | 1285 | 6 | ~1 |
| CPU (`to_result` + `other`) | 16 | – | 16 |
| **Total** | **~10,150** | **~47** | **~65 ms** |

With the API and DB in the same region, a round trip is typically **~1–3 ms**
(to be confirmed with `scripts/db_rtt.py` after the move):

| | Today (DB in Mumbai) | DB in Ohio (projected) |
|---|---|---|
| Network wait (~47 round trips) | ~10,080 ms | **~50–150 ms** |
| Real work | ~65 ms | ~65 ms |
| **`server.total`** | **10,151 ms** | **~120–250 ms** |
| **User in BD (`client_total`)** | **10,529 ms** | **~500–650 ms** (includes the unchanged ~380 ms BD ↔ Ohio leg) |
| User in the US | ~10.2 s | **~200–350 ms** |

That is about **40× faster on the server with no code changes**. Once the DB is
co-located, each query costs ~2 ms instead of ~640 ms, so the code-side fixes in
§5 become minor.

### Trade-offs of moving the DB

- **Local development from BD slows down.** The laptop's DB round trip goes from
  ~40 ms (BD → Mumbai) to BD → Ohio (likely ~250 ms+), so local requests would take
  roughly what Render takes today. The mitigation is developing against a local
  Postgres or a nearer Supabase branch.
- **It's a migration, not a setting.** A Supabase project's region can't be
  changed in place. It needs a new project in `us-east-2` and a data migration.
- **The instance is shared.** The `public` schema is owned by another org, so the
  move needs their agreement, and it changes their latency too.

### Alternative: co-locate in Singapore

Render Singapore + Supabase `ap-southeast-1` gets the same same-region round
trips (~1–3 ms) between API and DB. It also gives BD users a much shorter single
leg than Ohio, and local development from BD stays fast. US users would pay a
longer single leg instead. The choice depends on where most users are. **The
rule is to keep the API and the DB in the same region.**

---

## 7. Recommendations

1. **Co-locate the API and the DB** (Ohio or Singapore, depending on where most
   users are). This is the largest win by far: ~10 s → ~0.2 s server time.
2. **Ship `joinedload` for `detail` and `taxes`.** It's low risk, the response is
   unchanged, and it saves 2 queries.
3. **Decide on the lean list response** once the frontend's list-view fields are
   confirmed. It's the largest remaining code-side saving, plus payload size.
4. **Keep `PROFILING_ENABLED` available in dev** and re-run
   `scripts/bench_endpoint.py` after each change to verify it.
