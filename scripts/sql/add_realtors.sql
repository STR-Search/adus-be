-- Realtors lookup table + market_keys_master.realtor_ids.
--
-- These changes were folded into the init migration
-- (b35b5049dbae_init_markets_schema_tables.py) rather than shipped as a new
-- revision, so already-migrated databases need this run by hand:
--
--     psql "$DATABASE_URL" -f scripts/sql/add_realtors.sql
--
-- Idempotent — safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS markets.realtors (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR,
    email       VARCHAR,
    phone       VARCHAR,
    brokerage   VARCHAR,
    notes       VARCHAR,
    deleted_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Realtor identity is the email, matched case- and whitespace-insensitively so
-- the same contact cannot be entered twice; enforced only among active rows,
-- and rows without an email are exempt.
CREATE UNIQUE INDEX IF NOT EXISTS uq_realtors_email_active
    ON markets.realtors (lower(btrim(email)))
    WHERE deleted_at IS NULL AND email IS NOT NULL;

DROP TRIGGER IF EXISTS realtors_updated_at ON markets.realtors;
CREATE TRIGGER realtors_updated_at
    BEFORE UPDATE ON markets.realtors
    FOR EACH ROW EXECUTE FUNCTION markets.update_updated_at();

ALTER TABLE markets.market_keys_master
    ADD COLUMN IF NOT EXISTS realtor_ids INTEGER[];

COMMIT;
