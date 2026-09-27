-- One-off DDL to create the zillow schema (tables, views, functions, triggers,
-- indexes, constraints, grants) in a fresh Supabase project.
--
-- Generated from `pg_dump --schema-only --schema=zillow` against the source
-- project (Postgres 17.6), excluding zillow.backup_20260902_listings_wipe.
-- The zillow schema is owned by another team; adus-be does not manage it.
--
-- Prerequisite: markets.market_keys_master must exist in the destination
-- (run `uv run alembic upgrade heads` first) because zillow.scheduled_presets
-- has a foreign key to it.
--
-- Usage (either):
--   - Paste into the Supabase SQL editor of the NEW project and run, or
--   - psql "$DEV_DATABASE_URL" --set ON_ERROR_STOP=on -f scripts/seeding_scripts/zillow_schema.sql
--
-- Then load data with:
--   ./scripts/seeding_scripts/table_transfer_non_adus.sh --schema zillow --tables --all

BEGIN;

SET check_function_bodies = false;
SET client_min_messages = warning;
SELECT pg_catalog.set_config('search_path', '', true);

DO $$
BEGIN
    IF to_regclass('markets.market_keys_master') IS NULL THEN
        RAISE EXCEPTION 'markets.market_keys_master is missing; run alembic upgrade heads before this script';
    END IF;
END;
$$;

CREATE SCHEMA zillow;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

CREATE TABLE zillow.scheduled_presets (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    description text,
    search_url text NOT NULL,
    schedule_type text NOT NULL,
    schedule_config jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_active boolean DEFAULT true,
    last_run timestamp with time zone,
    next_run timestamp with time zone,
    last_daily_run timestamp with time zone,
    last_full_run timestamp with time zone,
    cycle_length_days integer DEFAULT 14,
    force_next_run_full boolean DEFAULT false,
    filter_template text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    market_id integer,
    is_default boolean DEFAULT false NOT NULL,
    preset_kind text DEFAULT 'acquisition'::text NOT NULL,
    CONSTRAINT ck_scheduled_presets_preset_kind CHECK ((preset_kind = ANY (ARRAY['acquisition'::text, 'sold'::text]))),
    CONSTRAINT scheduled_presets_schedule_type_check CHECK ((schedule_type = ANY (ARRAY['hourly'::text, 'daily'::text, 'weekly'::text, 'monthly'::text, 'every-x-minutes'::text, 'custom'::text, 'on-demand'::text])))
);

CREATE TABLE zillow.scheduled_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    preset_id uuid NOT NULL,
    started_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamp with time zone,
    status text,
    run_type text DEFAULT 'daily'::text,
    listings_scraped integer DEFAULT 0,
    new_listings integer DEFAULT 0,
    updated_listings integer DEFAULT 0,
    removed_listings integer DEFAULT 0,
    details_scraped integer DEFAULT 0,
    error_message text,
    result_data jsonb DEFAULT '{}'::jsonb,
    heartbeat_at timestamp with time zone,
    adus_triggered_at timestamp with time zone,
    manual boolean DEFAULT false NOT NULL,
    CONSTRAINT scheduled_runs_run_type_check CHECK ((run_type = ANY (ARRAY['daily'::text, 'full'::text]))),
    CONSTRAINT scheduled_runs_status_check CHECK ((status = ANY (ARRAY['queued'::text, 'running'::text, 'completed'::text, 'failed'::text])))
);

CREATE TABLE zillow.filter_templates (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    description text,
    is_system_template boolean DEFAULT false,
    created_by uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE zillow.template_filters (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    template_id uuid NOT NULL,
    field_name text NOT NULL,
    table_source text NOT NULL,
    filter_type text NOT NULL,
    operator text NOT NULL,
    filter_value text,
    fuzzy_match boolean DEFAULT false,
    filter_order integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT template_filters_filter_type_check CHECK ((filter_type = ANY (ARRAY['numeric'::text, 'boolean'::text, 'text'::text]))),
    CONSTRAINT template_filters_table_source_check CHECK ((table_source = ANY (ARRAY['scheduled_listings'::text, 'scheduled_listing_details'::text])))
);

CREATE TABLE zillow.preset_filters (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    preset_id uuid NOT NULL,
    template_id uuid,
    field_name text NOT NULL,
    table_source text NOT NULL,
    filter_type text NOT NULL,
    operator text NOT NULL,
    filter_value text,
    fuzzy_match boolean DEFAULT false,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT preset_filters_filter_type_check CHECK ((filter_type = ANY (ARRAY['numeric'::text, 'boolean'::text, 'text'::text]))),
    CONSTRAINT preset_filters_table_source_check CHECK ((table_source = ANY (ARRAY['scheduled_listings'::text, 'scheduled_listing_details'::text])))
);

CREATE TABLE zillow.scheduled_listings (
    zpid text NOT NULL,
    preset_id uuid NOT NULL,
    img_src text,
    detail_url text,
    price text,
    unformatted_price text,
    address text,
    address_street text,
    address_city text,
    address_state text,
    address_zipcode text,
    beds integer,
    baths double precision,
    area integer,
    latitude double precision,
    longitude double precision,
    home_type text,
    home_status text,
    time_on_zillow text,
    flex_text text,
    keep_updated boolean DEFAULT true,
    remove_listing boolean DEFAULT false,
    last_seen timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    passes_preset_filters boolean
);

CREATE TABLE zillow.scheduled_listing_details (
    zpid text NOT NULL,
    preset_id uuid NOT NULL,
    city text,
    state text,
    home_status text,
    address jsonb,
    bedrooms integer,
    bathrooms double precision,
    price double precision,
    year_built integer,
    street_address text,
    zipcode text,
    home_type text,
    monthly_hoa_fee double precision,
    living_area integer,
    living_area_value double precision,
    zestimate double precision,
    rent_zestimate double precision,
    schools jsonb,
    tax_history jsonb,
    price_history jsonb,
    description text,
    latitude double precision,
    longitude double precision,
    broker_name text,
    lot_size_sqft double precision,
    lot_size_acre double precision,
    original_photos jsonb,
    photo_count integer,
    mortgage_rates jsonb,
    price_change double precision,
    price_change_date date,
    last_sold_price double precision,
    reso_facts jsonb,
    home_insights text,
    view text,
    sewer text,
    cooling text,
    heating text,
    furnished boolean,
    parking_capacity double precision,
    has_garage boolean,
    fencing text,
    flooring text,
    pool_features text,
    agent_name text,
    agent_contact_info text,
    broker_contact_info text,
    mlsid text,
    mls_name text,
    neighborhood_name text,
    parcel_id text,
    tax_assessed_value double precision,
    last_updated_in_zillow timestamp with time zone,
    keep_updated boolean DEFAULT true,
    remove_listing boolean DEFAULT false,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT scheduled_listing_details_photo_count_check CHECK ((photo_count >= 0))
);

CREATE TABLE zillow.sold_listings (
    zpid text NOT NULL,
    preset_id uuid NOT NULL,
    img_src text,
    detail_url text,
    price text,
    unformatted_price text,
    address text,
    address_street text,
    address_city text,
    address_state text,
    address_zipcode text,
    beds integer,
    baths double precision,
    area integer,
    latitude double precision,
    longitude double precision,
    home_type text,
    home_status text,
    time_on_zillow text,
    flex_text text,
    keep_updated boolean DEFAULT true,
    remove_listing boolean DEFAULT false,
    last_seen timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    passes_preset_filters boolean
);

-- Constraint name mirrors the source (copied from scheduled_listing_details).
CREATE TABLE zillow.sold_listing_details (
    zpid text NOT NULL,
    preset_id uuid NOT NULL,
    city text,
    state text,
    home_status text,
    address jsonb,
    bedrooms integer,
    bathrooms double precision,
    price double precision,
    year_built integer,
    street_address text,
    zipcode text,
    home_type text,
    monthly_hoa_fee double precision,
    living_area integer,
    living_area_value double precision,
    zestimate double precision,
    rent_zestimate double precision,
    schools jsonb,
    tax_history jsonb,
    price_history jsonb,
    description text,
    latitude double precision,
    longitude double precision,
    broker_name text,
    lot_size_sqft double precision,
    lot_size_acre double precision,
    original_photos jsonb,
    photo_count integer,
    mortgage_rates jsonb,
    price_change double precision,
    price_change_date date,
    last_sold_price double precision,
    reso_facts jsonb,
    home_insights text,
    view text,
    sewer text,
    cooling text,
    heating text,
    furnished boolean,
    parking_capacity double precision,
    has_garage boolean,
    fencing text,
    flooring text,
    pool_features text,
    agent_name text,
    agent_contact_info text,
    broker_contact_info text,
    mlsid text,
    mls_name text,
    neighborhood_name text,
    parcel_id text,
    tax_assessed_value double precision,
    last_updated_in_zillow timestamp with time zone,
    keep_updated boolean DEFAULT true,
    remove_listing boolean DEFAULT false,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT scheduled_listing_details_photo_count_check CHECK ((photo_count >= 0))
);

-- ---------------------------------------------------------------------------
-- Primary keys and unique constraints
-- ---------------------------------------------------------------------------

ALTER TABLE ONLY zillow.filter_templates ADD CONSTRAINT filter_templates_pkey PRIMARY KEY (id);
ALTER TABLE ONLY zillow.filter_templates ADD CONSTRAINT filter_templates_name_key UNIQUE (name);
ALTER TABLE ONLY zillow.preset_filters ADD CONSTRAINT preset_filters_pkey PRIMARY KEY (id);
ALTER TABLE ONLY zillow.scheduled_listing_details ADD CONSTRAINT scheduled_listing_details_pkey PRIMARY KEY (zpid);
ALTER TABLE ONLY zillow.scheduled_listings ADD CONSTRAINT scheduled_listings_pkey PRIMARY KEY (zpid);
ALTER TABLE ONLY zillow.scheduled_presets ADD CONSTRAINT scheduled_presets_pkey PRIMARY KEY (id);
ALTER TABLE ONLY zillow.scheduled_runs ADD CONSTRAINT scheduled_runs_pkey PRIMARY KEY (id);
ALTER TABLE ONLY zillow.sold_listing_details ADD CONSTRAINT sold_listing_details_pkey PRIMARY KEY (zpid);
ALTER TABLE ONLY zillow.sold_listings ADD CONSTRAINT sold_listings_pkey PRIMARY KEY (zpid);
ALTER TABLE ONLY zillow.template_filters ADD CONSTRAINT template_filters_pkey PRIMARY KEY (id);

-- ---------------------------------------------------------------------------
-- Foreign keys
-- ---------------------------------------------------------------------------

ALTER TABLE ONLY zillow.scheduled_presets
    ADD CONSTRAINT scheduled_presets_market_id_fkey FOREIGN KEY (market_id) REFERENCES markets.market_keys_master(id);
ALTER TABLE ONLY zillow.scheduled_runs
    ADD CONSTRAINT scheduled_runs_preset_id_fkey FOREIGN KEY (preset_id) REFERENCES zillow.scheduled_presets(id) ON DELETE CASCADE;
ALTER TABLE ONLY zillow.template_filters
    ADD CONSTRAINT template_filters_template_id_fkey FOREIGN KEY (template_id) REFERENCES zillow.filter_templates(id) ON DELETE CASCADE;
ALTER TABLE ONLY zillow.preset_filters
    ADD CONSTRAINT preset_filters_preset_id_fkey FOREIGN KEY (preset_id) REFERENCES zillow.scheduled_presets(id) ON DELETE CASCADE;
ALTER TABLE ONLY zillow.preset_filters
    ADD CONSTRAINT preset_filters_template_id_fkey FOREIGN KEY (template_id) REFERENCES zillow.filter_templates(id);
ALTER TABLE ONLY zillow.scheduled_listings
    ADD CONSTRAINT scheduled_listings_preset_id_fkey FOREIGN KEY (preset_id) REFERENCES zillow.scheduled_presets(id) ON DELETE CASCADE;
ALTER TABLE ONLY zillow.scheduled_listing_details
    ADD CONSTRAINT scheduled_listing_details_preset_id_fkey FOREIGN KEY (preset_id) REFERENCES zillow.scheduled_presets(id) ON DELETE CASCADE;
ALTER TABLE ONLY zillow.scheduled_listing_details
    ADD CONSTRAINT scheduled_listing_details_zpid_fkey FOREIGN KEY (zpid) REFERENCES zillow.scheduled_listings(zpid) ON DELETE CASCADE;
ALTER TABLE ONLY zillow.sold_listings
    ADD CONSTRAINT fk_sold_listings_preset FOREIGN KEY (preset_id) REFERENCES zillow.scheduled_presets(id) ON DELETE CASCADE;
ALTER TABLE ONLY zillow.sold_listing_details
    ADD CONSTRAINT fk_sold_listing_details_preset FOREIGN KEY (preset_id) REFERENCES zillow.scheduled_presets(id) ON DELETE CASCADE;
ALTER TABLE ONLY zillow.sold_listing_details
    ADD CONSTRAINT fk_sold_listing_details_listing FOREIGN KEY (zpid) REFERENCES zillow.sold_listings(zpid) ON DELETE CASCADE;

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE INDEX idx_filter_templates_name ON zillow.filter_templates USING btree (name);
CREATE INDEX idx_filter_templates_system ON zillow.filter_templates USING btree (is_system_template);

CREATE INDEX idx_template_filters_field_name ON zillow.template_filters USING btree (field_name);
CREATE INDEX idx_template_filters_template_id ON zillow.template_filters USING btree (template_id);

CREATE INDEX idx_preset_filters_active ON zillow.preset_filters USING btree (is_active);
CREATE INDEX idx_preset_filters_field_name ON zillow.preset_filters USING btree (field_name);
CREATE INDEX idx_preset_filters_preset_id ON zillow.preset_filters USING btree (preset_id);
CREATE INDEX idx_preset_filters_template_id ON zillow.preset_filters USING btree (template_id);

CREATE INDEX idx_scheduled_presets_cycle_length_days ON zillow.scheduled_presets USING btree (cycle_length_days);
CREATE INDEX idx_scheduled_presets_force_next_run_full ON zillow.scheduled_presets USING btree (force_next_run_full);
CREATE INDEX idx_scheduled_presets_last_daily_run ON zillow.scheduled_presets USING btree (last_daily_run);
CREATE INDEX idx_scheduled_presets_last_full_run ON zillow.scheduled_presets USING btree (last_full_run);
CREATE INDEX idx_scheduled_presets_market_id ON zillow.scheduled_presets USING btree (market_id);
CREATE UNIQUE INDEX ux_scheduled_presets_default_market ON zillow.scheduled_presets USING btree (COALESCE(market_id, '-1'::integer)) WHERE is_default;

CREATE UNIQUE INDEX idx_scheduled_runs_one_active_per_preset ON zillow.scheduled_runs USING btree (preset_id) WHERE (status = ANY (ARRAY['queued'::text, 'running'::text]));
CREATE INDEX idx_scheduled_runs_preset_id ON zillow.scheduled_runs USING btree (preset_id);
CREATE INDEX idx_scheduled_runs_queued ON zillow.scheduled_runs USING btree (started_at) WHERE (status = 'queued'::text);
CREATE INDEX idx_scheduled_runs_run_type ON zillow.scheduled_runs USING btree (run_type);
CREATE INDEX idx_scheduled_runs_started_at ON zillow.scheduled_runs USING btree (started_at);

CREATE INDEX idx_scheduled_listings_keep_updated ON zillow.scheduled_listings USING btree (keep_updated);
CREATE INDEX idx_scheduled_listings_last_seen ON zillow.scheduled_listings USING btree (last_seen);
CREATE INDEX idx_scheduled_listings_passes_filter ON zillow.scheduled_listings USING btree (passes_preset_filters);
CREATE INDEX idx_scheduled_listings_preset_id ON zillow.scheduled_listings USING btree (preset_id);
CREATE INDEX idx_scheduled_listings_remove_listing ON zillow.scheduled_listings USING btree (remove_listing);

CREATE INDEX idx_scheduled_listing_details_cooling ON zillow.scheduled_listing_details USING btree (cooling);
CREATE INDEX idx_scheduled_listing_details_fencing ON zillow.scheduled_listing_details USING btree (fencing);
CREATE INDEX idx_scheduled_listing_details_flooring ON zillow.scheduled_listing_details USING btree (flooring);
CREATE INDEX idx_scheduled_listing_details_furnished ON zillow.scheduled_listing_details USING btree (furnished);
CREATE INDEX idx_scheduled_listing_details_has_garage ON zillow.scheduled_listing_details USING btree (has_garage);
CREATE INDEX idx_scheduled_listing_details_heating ON zillow.scheduled_listing_details USING btree (heating);
CREATE INDEX idx_scheduled_listing_details_keep_updated ON zillow.scheduled_listing_details USING btree (keep_updated);
CREATE INDEX idx_scheduled_listing_details_lot_size_acre ON zillow.scheduled_listing_details USING btree (lot_size_acre);
CREATE INDEX idx_scheduled_listing_details_lot_size_sqft ON zillow.scheduled_listing_details USING btree (lot_size_sqft);
CREATE INDEX idx_scheduled_listing_details_parking_capacity ON zillow.scheduled_listing_details USING btree (parking_capacity);
CREATE INDEX idx_scheduled_listing_details_photo_count ON zillow.scheduled_listing_details USING btree (photo_count);
CREATE INDEX idx_scheduled_listing_details_pool_features ON zillow.scheduled_listing_details USING btree (pool_features);
CREATE INDEX idx_scheduled_listing_details_preset_id ON zillow.scheduled_listing_details USING btree (preset_id);
CREATE INDEX idx_scheduled_listing_details_remove_listing ON zillow.scheduled_listing_details USING btree (remove_listing);
CREATE INDEX idx_scheduled_listing_details_sewer ON zillow.scheduled_listing_details USING btree (sewer);
CREATE INDEX idx_scheduled_listing_details_view ON zillow.scheduled_listing_details USING btree (view);

CREATE INDEX sold_listings_keep_updated_idx ON zillow.sold_listings USING btree (keep_updated);
CREATE INDEX sold_listings_last_seen_idx ON zillow.sold_listings USING btree (last_seen);
CREATE INDEX sold_listings_passes_preset_filters_idx ON zillow.sold_listings USING btree (passes_preset_filters);
CREATE INDEX sold_listings_preset_id_idx ON zillow.sold_listings USING btree (preset_id);
CREATE INDEX sold_listings_remove_listing_idx ON zillow.sold_listings USING btree (remove_listing);

CREATE INDEX sold_listing_details_cooling_idx ON zillow.sold_listing_details USING btree (cooling);
CREATE INDEX sold_listing_details_fencing_idx ON zillow.sold_listing_details USING btree (fencing);
CREATE INDEX sold_listing_details_flooring_idx ON zillow.sold_listing_details USING btree (flooring);
CREATE INDEX sold_listing_details_furnished_idx ON zillow.sold_listing_details USING btree (furnished);
CREATE INDEX sold_listing_details_has_garage_idx ON zillow.sold_listing_details USING btree (has_garage);
CREATE INDEX sold_listing_details_heating_idx ON zillow.sold_listing_details USING btree (heating);
CREATE INDEX sold_listing_details_keep_updated_idx ON zillow.sold_listing_details USING btree (keep_updated);
CREATE INDEX sold_listing_details_lot_size_acre_idx ON zillow.sold_listing_details USING btree (lot_size_acre);
CREATE INDEX sold_listing_details_lot_size_sqft_idx ON zillow.sold_listing_details USING btree (lot_size_sqft);
CREATE INDEX sold_listing_details_parking_capacity_idx ON zillow.sold_listing_details USING btree (parking_capacity);
CREATE INDEX sold_listing_details_photo_count_idx ON zillow.sold_listing_details USING btree (photo_count);
CREATE INDEX sold_listing_details_pool_features_idx ON zillow.sold_listing_details USING btree (pool_features);
CREATE INDEX sold_listing_details_preset_id_idx ON zillow.sold_listing_details USING btree (preset_id);
CREATE INDEX sold_listing_details_remove_listing_idx ON zillow.sold_listing_details USING btree (remove_listing);
CREATE INDEX sold_listing_details_sewer_idx ON zillow.sold_listing_details USING btree (sewer);
CREATE INDEX sold_listing_details_view_idx ON zillow.sold_listing_details USING btree (view);

-- ---------------------------------------------------------------------------
-- Functions
-- ---------------------------------------------------------------------------

CREATE FUNCTION zillow.claim_next_run() RETURNS SETOF zillow.scheduled_runs
    LANGUAGE plpgsql
    AS $$
DECLARE
    claimed_id UUID;
BEGIN
    SELECT id INTO claimed_id
    FROM zillow.scheduled_runs
    WHERE status = 'queued'
    ORDER BY started_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1;

    IF claimed_id IS NULL THEN
        RETURN;  -- nothing queued -> empty set
    END IF;

    RETURN QUERY
    UPDATE zillow.scheduled_runs
    SET status = 'running',
        started_at = CURRENT_TIMESTAMP,   -- started_at now marks processing start
        heartbeat_at = CURRENT_TIMESTAMP
    WHERE id = claimed_id
    RETURNING *;
END;
$$;

CREATE FUNCTION zillow.get_column_type(p_table_name text, p_column_name text) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE
    data_type TEXT;
BEGIN
    SELECT c.data_type INTO data_type
    FROM information_schema.columns c
    WHERE c.table_schema = 'zillow'
      AND c.table_name = p_table_name
      AND c.column_name = p_column_name
    LIMIT 1;
    RETURN data_type;
END;
$$;

CREATE FUNCTION zillow.get_filter_type(p_table_name text, p_column_name text) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE
    data_type TEXT;
    filter_type TEXT;
BEGIN
    SELECT zillow.get_column_type(p_table_name, p_column_name) INTO data_type;
    IF data_type IN ('integer', 'bigint', 'smallint', 'numeric', 'decimal', 'real', 'double precision') THEN
        filter_type := 'numeric';
    ELSIF data_type IN ('boolean') THEN
        filter_type := 'boolean';
    ELSE
        filter_type := 'text';
    END IF;
    RETURN filter_type;
END;
$$;

CREATE FUNCTION zillow.get_keep_updated_listings(preset_uuid uuid) RETURNS TABLE(zpid text, preset_id uuid, address text, price text, unformatted_price text, beds integer, baths double precision, keep_updated boolean, last_seen timestamp with time zone, city text, state text, bedrooms integer, bathrooms double precision, year_built integer, description text, zestimate double precision, price_change double precision, updated_at timestamp with time zone)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        sl.zpid, sl.preset_id, sl.address, sl.price, sl.unformatted_price,
        sl.beds, sl.baths, sl.keep_updated, sl.last_seen,
        sld.city, sld.state, sld.bedrooms, sld.bathrooms,
        sld.year_built, sld.description, sld.zestimate,
        sld.price_change, sld.updated_at
    FROM zillow.scheduled_listings sl
    LEFT JOIN zillow.scheduled_listing_details sld ON sl.zpid = sld.zpid
    WHERE sl.preset_id = preset_uuid AND sl.keep_updated = true
    ORDER BY sl.last_seen DESC;
END;
$$;

CREATE FUNCTION zillow.get_preset_stats(preset_uuid uuid) RETURNS TABLE(total_listings integer, keep_updated_count integer, last_run timestamp with time zone, next_run timestamp with time zone, is_active boolean)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(sl.zpid)::INTEGER AS total_listings,
        COUNT(CASE WHEN sl.keep_updated = true THEN 1 END)::INTEGER AS keep_updated_count,
        sp.last_run, sp.next_run, sp.is_active
    FROM zillow.scheduled_presets sp
    LEFT JOIN zillow.scheduled_listings sl ON sp.id = sl.preset_id
    WHERE sp.id = preset_uuid
    GROUP BY sp.id, sp.last_run, sp.next_run, sp.is_active;
END;
$$;

CREATE FUNCTION zillow.mark_listings_inactive(preset_uuid uuid, zpid_list text[]) RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    UPDATE zillow.scheduled_listings
    SET keep_updated = false, updated_at = CURRENT_TIMESTAMP
    WHERE preset_id = preset_uuid AND zpid = ANY(zpid_list);

    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$;

CREATE FUNCTION zillow.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- Triggers
-- ---------------------------------------------------------------------------

CREATE TRIGGER update_scheduled_presets_updated_at BEFORE UPDATE ON zillow.scheduled_presets FOR EACH ROW EXECUTE FUNCTION zillow.update_updated_at_column();
CREATE TRIGGER update_scheduled_listings_updated_at BEFORE UPDATE ON zillow.scheduled_listings FOR EACH ROW EXECUTE FUNCTION zillow.update_updated_at_column();
CREATE TRIGGER update_scheduled_listing_details_updated_at BEFORE UPDATE ON zillow.scheduled_listing_details FOR EACH ROW EXECUTE FUNCTION zillow.update_updated_at_column();
CREATE TRIGGER update_sold_listings_updated_at BEFORE UPDATE ON zillow.sold_listings FOR EACH ROW EXECUTE FUNCTION zillow.update_updated_at_column();
CREATE TRIGGER update_sold_listing_details_updated_at BEFORE UPDATE ON zillow.sold_listing_details FOR EACH ROW EXECUTE FUNCTION zillow.update_updated_at_column();

-- ---------------------------------------------------------------------------
-- Views
-- ---------------------------------------------------------------------------

CREATE VIEW zillow.keep_updated_listings_view AS
 SELECT sl.zpid,
    sl.preset_id,
    sp.name AS preset_name,
    sl.address,
    sl.price,
    sl.unformatted_price,
    sl.beds,
    sl.baths,
    sl.keep_updated,
    sl.last_seen,
    sld.city,
    sld.state,
    sld.bedrooms,
    sld.bathrooms,
    sld.year_built,
    sld.description,
    sld.zestimate,
    sld.price_change,
    sld.updated_at
   FROM ((zillow.scheduled_listings sl
     JOIN zillow.scheduled_presets sp ON ((sl.preset_id = sp.id)))
     LEFT JOIN zillow.scheduled_listing_details sld ON ((sl.zpid = sld.zpid)))
  WHERE (sl.keep_updated = true)
  ORDER BY sl.last_seen DESC;

CREATE VIEW zillow.preset_stats_view AS
 SELECT sp.id,
    sp.name,
    sp.schedule_type,
    sp.is_active,
    sp.last_run,
    sp.next_run,
    count(sl.zpid) AS total_listings,
    count(
        CASE
            WHEN (sl.keep_updated = true) THEN 1
            ELSE NULL::integer
        END) AS keep_updated_count,
    count(
        CASE
            WHEN (sl.keep_updated = false) THEN 1
            ELSE NULL::integer
        END) AS inactive_count
   FROM (zillow.scheduled_presets sp
     LEFT JOIN zillow.scheduled_listings sl ON ((sp.id = sl.preset_id)))
  GROUP BY sp.id, sp.name, sp.schedule_type, sp.is_active, sp.last_run, sp.next_run;

-- ---------------------------------------------------------------------------
-- Grants (mirror the source: Supabase API roles get full access, RLS is off)
-- ---------------------------------------------------------------------------

GRANT USAGE ON SCHEMA zillow TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA zillow TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA zillow TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA zillow TO anon, authenticated, service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA zillow GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA zillow GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA zillow GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;

COMMIT;
