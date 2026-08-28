-- Identify the rows written by scripts/backfill_underwriting_zpids.py that now
-- share a zpid with a pre-existing deal for the same property -- the population
-- the backfill's closing NOTE counts but does not name.
--
-- -- 1. discovery: find the backfill transaction
-- psql "$DATABASE_URL" -f scripts/sql/find_backfilled_zpid_collisions.sql
--
-- -- 2. report: pass the txid whose row count matches the run's "updated"
-- psql "$DATABASE_URL" -v txid=166455 \
-- -f scripts/sql/find_backfilled_zpid_collisions.sql
--
-- -- 3. same thing as a CSV of just the collision list
-- psql "$DATABASE_URL" -v txid=166455 -v csv=1 -q --csv \
-- -f scripts/sql/find_backfilled_zpid_collisions.sql \
-- > scripts/data/zpid_collisions.csv
--

-- Read-only: every statement is a SELECT, inside a READ ONLY transaction.
--
-- WHY xmin. The backfill ran as one set-based UPDATE in one transaction, so
-- every row it touched carries the same xmin. Nothing else marks them:
-- iron_bank.underwritings has no updated_at trigger (unlike users, api_keys,
-- market_keys_master and realtors), and the script's raw text() UPDATE bypasses
-- SQLAlchemy's onupdate=func.now(), so updated_at was never bumped.
--
-- WHEN THIS STOPS WORKING. xmin identifies the *last* transaction to write each
-- row. Any later write -- price reconciliation above all, which now reaches
-- these rows precisely because the backfill worked -- moves that row into a new
-- xmin and out of the group. Run this before the next reconciliation pass and
-- persist the ids; STEP 4 is the (wider, heuristic) fallback once the group has
-- fragmented. A vacuum freeze would also collapse xmin, though not on a table
-- this young.
--
-- Run against prod 2026-08-28: txid 166455, 120 rows updated, 106 colliding
-- across 91 distinct properties (15 properties took two backfilled rows each
-- and so carry three series, not two); 99 legacy_sheet / 7 adus, all
-- is_automated = false; 48 of the 106 differ in purchase_price from the deal
-- they collided with.

  

BEGIN;
SET TRANSACTION READ ONLY;

  

\if :{?txid}

  

-- ---------------------------------------------------------------------------

-- The backfilled rows, and the subset that collided.

--

-- series_id matters twice over. Versions of one series legitimately share a

-- zpid, so `o.series_id <> b.series_id` is what keeps a deal's own duplicates

-- from counting as a collision -- the backfill script needed no such guard

-- (its candidates had a NULL zpid, so their own versions could not match) but a

-- post-hoc query does. And `o.id NOT IN (SELECT id FROM backfilled)` restricts

-- the other side to genuinely pre-existing deals, reproducing the semantics of

-- the script's EXISTS, which ran against pre-UPDATE state.

--

-- Held in a psql variable and pasted into each query rather than as a temp

-- view: a READ ONLY transaction disallows every CREATE, temporary or not.

-- ---------------------------------------------------------------------------

\set cte 'WITH backfilled AS (SELECT id, series_id, zpid, source, is_automated, property_address, purchase_price, deal_status, listing_url FROM iron_bank.underwritings WHERE xmin::text::bigint = ' :txid '), colliding AS (SELECT b.* FROM backfilled b WHERE EXISTS (SELECT 1 FROM iron_bank.underwritings o WHERE o.zpid = b.zpid AND o.series_id <> b.series_id AND o.id NOT IN (SELECT id FROM backfilled)))'

  

-- With -v csv=1 the summary blocks and their \echo headers are skipped, so

-- stdout is nothing but STEP 3's result set and pipes straight to a file.

\if :{?csv}

\else

  

\echo '== STEP 2a: sanity check -- sharing count should equal the run''s NOTE =='

:cte

SELECT (SELECT count(*) FROM backfilled) AS backfilled_rows,

(SELECT count(*) FROM colliding) AS sharing_zpid_with_existing_deal;

  

\echo ''

\echo '== STEP 2b: shape =='

:cte

SELECT count(*) AS colliding_rows,

count(DISTINCT zpid) AS distinct_properties,

count(DISTINCT series_id) AS distinct_backfilled_series

FROM colliding;

  

\echo ''

\echo '== STEP 2c: provenance =='

:cte

SELECT COALESCE(source, 'unknown') AS source, is_automated, count(*) AS rows

FROM colliding

GROUP BY 1, 2

ORDER BY rows DESC;

  

-- Counting both sides. Anything above 2 is a property where more than one

-- backfilled deal landed on the same zpid, so a merge scoped as "collapse the

-- pair" will not fit it.

\echo ''

\echo '== STEP 2d: total series per affected property =='

:cte

SELECT series_at_property, count(*) AS properties FROM (

SELECT (SELECT count(DISTINCT u.series_id)

FROM iron_bank.underwritings u WHERE u.zpid = c.zpid)

AS series_at_property

FROM (SELECT DISTINCT zpid FROM colliding) c

) t

GROUP BY 1 ORDER BY 1;

  

\echo ''

\echo '== STEP 2e: properties that took more than one backfilled row =='

:cte

SELECT zpid,

count(*) AS backfilled_rows_here,

array_agg(id ORDER BY id) AS backfilled_ids,

min(property_address) AS property_address

FROM colliding

GROUP BY zpid

HAVING count(*) > 1

ORDER BY backfilled_rows_here DESC, zpid;

  

-- What reconciliation will now drive on both series independently.

\echo ''

\echo '== STEP 2f: purchase-price divergence within each pair =='

:cte

SELECT count(*) FILTER (WHERE c.purchase_price IS DISTINCT FROM o.purchase_price)

AS differing_purchase_price,

count(*) FILTER (WHERE c.purchase_price IS NULL) AS backfilled_price_null,

count(*) AS pairs

FROM colliding c

JOIN LATERAL (

SELECT purchase_price FROM iron_bank.underwritings o

WHERE o.zpid = c.zpid AND o.series_id <> c.series_id

ORDER BY o.id DESC LIMIT 1

) o ON TRUE;

  

\echo ''

\echo '== STEP 3: the collisions, one row per backfilled deal =='

  

\endif

  

-- The list itself.

  

:cte

SELECT c.id AS backfilled_id,

c.series_id AS backfilled_series_id,

c.source AS backfilled_source,

c.is_automated AS backfilled_is_automated,

c.zpid,

c.property_address AS backfilled_property_address,

c.purchase_price AS backfilled_purchase_price,

c.deal_status AS backfilled_deal_status,

count(DISTINCT o.series_id) AS colliding_series,

array_agg(DISTINCT o.id ORDER BY o.id) AS existing_ids,

array_agg(DISTINCT COALESCE(o.source,'unknown')) AS existing_sources,

array_agg(DISTINCT o.purchase_price) AS existing_purchase_prices,

-- The other side's address, and whether it matches. Without these the

-- report looks wrong on the 12 pairs whose address strings diverge

-- ("Saint Augustine" vs "St. Augustine"), where searching the backfilled

-- address returns one row and the collision appears to be phantom.

-- zpid is the identity here; property_address is denormalized text and

-- is not reliable for matching -- which is the whole reason these rows

-- were invisible to the zpid-keyed jobs before the backfill.

array_agg(DISTINCT o.property_address) AS existing_property_addresses,

bool_and(o.property_address IS NOT DISTINCT FROM c.property_address)

AS address_strings_match,

bool_and(o.listing_url IS NOT DISTINCT FROM c.listing_url)

AS listing_urls_match

FROM colliding c

JOIN iron_bank.underwritings o

ON o.zpid = c.zpid

AND o.series_id <> c.series_id

AND o.id NOT IN (SELECT id FROM backfilled)

GROUP BY c.id, c.series_id, c.source, c.is_automated, c.zpid,

c.property_address, c.purchase_price, c.deal_status

ORDER BY c.zpid, c.id;

  

\else

  

\echo '== STEP 1: candidate backfill transactions =='

\echo 'Pick the txid whose "rows" equals the "updated" count the backfill'

\echo 'printed, then re-run with: -v txid=<txid>'

\echo ''

SELECT xmin::text::bigint AS txid,

count(*) AS rows,

count(*) FILTER (WHERE source = 'legacy_sheet') AS legacy_sheet_rows,

count(*) FILTER (WHERE is_automated IS NOT TRUE) AS non_automated_rows,

min(id) AS min_id,

max(id) AS max_id

FROM iron_bank.underwritings

WHERE zpid IS NOT NULL

GROUP BY 1

ORDER BY rows DESC

LIMIT 10;

  

-- Only reachable when xmin no longer isolates the backfill (later writes have

-- split it across transactions, so no group in STEP 1 matches the run's count).

-- Reconstructs candidates from provenance instead: every zpid held by more than

-- one series where a legacy/non-automated deal sits alongside an automated adus

-- one. Deliberately wider than the true set -- a superset to eyeball, not an

-- answer, and it cannot tell which side the backfill wrote.

\echo ''

\echo '== STEP 4 (fallback): provenance-based superset =='

SELECT u.zpid,

count(DISTINCT u.series_id) AS series_at_this_zpid,

array_agg(DISTINCT u.id ORDER BY u.id) AS underwriting_ids,

array_agg(DISTINCT COALESCE(u.source, 'unknown')) AS sources,

min(u.property_address) AS property_address

FROM iron_bank.underwritings u

WHERE u.zpid IS NOT NULL

GROUP BY u.zpid

HAVING count(DISTINCT u.series_id) > 1

AND bool_or(u.source = 'legacy_sheet' OR u.is_automated IS NOT TRUE)

AND bool_or(u.source = 'adus' AND u.is_automated IS TRUE)

ORDER BY series_at_this_zpid DESC, u.zpid;

  

\endif

  

COMMIT;