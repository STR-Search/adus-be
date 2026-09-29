#!/usr/bin/env bash

# Usage (run from the repository root):
#   export SOURCE_DATABASE_URL=postgresql://postgres.<source-ref>:<password>@<pooler-host>:5432/postgres
#   export DEV_DATABASE_URL=postgresql://postgres.<dev-ref>:<password>@<pooler-host>:5432/postgres
#   PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH" \
#     ./scripts/seeding_scripts/table_transfer_non_adus.sh --schema public \
#       --tables --all

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: table_transfer_non_adus.sh --schema SCHEMA --tables TABLE[,TABLE...]
       table_transfer_non_adus.sh --schema SCHEMA --tables --all

Copy data from SOURCE_DATABASE_URL to DEV_DATABASE_URL.
Configure schemas and tables in schema_tables() before transferring data.
Configured schemas: comps, zillow, public.
--all uses the maintained table catalog in this script (not DB discovery).
Both options are required. Explicit tables are copied in the supplied order;
list referenced/parent tables first.
Existing destination data is truncated with CASCADE, which can also
empty dependent tables outside this list. Destination tables must exist.

Example:
  ./scripts/seeding_scripts/table_transfer_non_adus.sh --schema public --tables --all
USAGE
}

fail() {
  echo "Error: $*" >&2
  exit 1
}

# Other teams' table catalog, populated before each transfer as needed.
# List referenced/parent tables before child tables. Add a case for each schema.
# Cross-schema prerequisites must already exist in the destination.
# Keep migration bookkeeping tables (such as alembic_version) out of this list.
schema_tables() {
  case "$1" in
    comps)
      SCHEMA_TABLES=(
        comps_tags
        comps_properties
      )
      ;;
    zillow)
      SCHEMA_TABLES=(
        filter_templates
        scheduled_presets
        preset_filters
        template_filters
        scheduled_listings
        scheduled_listing_details
        scheduled_runs
        sold_listings
        sold_listing_details
      )
      ;;
    public)
      SCHEMA_TABLES=(
        processing_executions
        # base_table_data
        # cleaned_data
        # market_run_exceptions
        # market_run_output
        # run_tracking
        # market_scrape_state
        # run_url_results
        # scrape_cycle_state
        # sp_profiles
        # sp_announcements
        # sp_comments
        # sp_flags
        # sp_notes
        # sp_promos
        # sp_quiz_scores
      )
      ;;
    # Add other schema cases here, each assigning SCHEMA_TABLES.
    *) fail "Unknown schema: $1. Configure it in schema_tables() first" ;;
  esac
  [[ ${#SCHEMA_TABLES[@]} -gt 0 ]] || fail "No tables configured for schema: $1. Populate schema_tables() first"
}

SCHEMA=""
TABLE_LIST=""
while (( $# > 0 )); do
  case "$1" in
    --schema)
      [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || fail "--schema requires a value"
      [[ -z "$SCHEMA" ]] || fail "--schema may only be supplied once"
      SCHEMA="$2"
      shift 2
      ;;
    --tables)
      [[ $# -ge 2 && -n "$2" ]] || fail "--tables requires a value"
      [[ -z "$TABLE_LIST" ]] || fail "--tables may only be supplied once"
      if [[ "$2" == --all ]]; then
        TABLE_LIST="--all"
        shift 2
      else
        shift
        while (( $# > 0 )) && [[ "$1" != --* ]]; do
          TABLE_LIST+=" $1"
          shift
        done
        [[ -n "$TABLE_LIST" ]] || fail "--tables requires a value"
      fi
      ;;
    -h|--help) usage; exit 0 ;;
    *) fail "Unknown argument: $1 (see --help)" ;;
  esac
done

[[ -n "$SCHEMA" && -n "$TABLE_LIST" ]] || fail "--schema and --tables are required (see --help)"
[[ "$SCHEMA" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || fail "Invalid schema name: $SCHEMA"
schema_tables "$SCHEMA"
if [[ "$TABLE_LIST" == --all ]]; then
  TABLES=("${SCHEMA_TABLES[@]}")
else
  [[ "$TABLE_LIST" != *$'\n'* ]] || fail "Invalid table list"
  [[ "$TABLE_LIST" != *, ]] || fail "Empty table name"
  IFS=',' read -r -a TABLES <<< "$TABLE_LIST"
  for i in "${!TABLES[@]}"; do
    table="${TABLES[$i]}"
    # Trim surrounding whitespace, including spaces after commas.
    table="${table#"${table%%[![:space:]]*}"}"
    table="${table%"${table##*[![:space:]]}"}"
    [[ "$table" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || fail "Invalid table name: $table"
    found=false
    for allowed in "${SCHEMA_TABLES[@]}"; do
      if [[ "$table" == "$allowed" ]]; then
        found=true
        break
      fi
    done
    [[ "$found" == true ]] || fail "Unknown table for $SCHEMA: $table"
    TABLES[$i]="$table"
  done
fi

[[ -n "${SOURCE_DATABASE_URL:-}" ]] || fail "Export SOURCE_DATABASE_URL first"
[[ -n "${DEV_DATABASE_URL:-}" ]] || fail "Export DEV_DATABASE_URL first"
command -v pg_dump >/dev/null || fail "pg_dump is required"
command -v psql >/dev/null || fail "psql is required"

printf 'Tables to transfer (in order):\n'
for table in "${TABLES[@]}"; do
  printf '  %s.%s\n' "$SCHEMA" "$table"
done

DUMP_DIR="$(mktemp -d)"
trap 'rm -rf "$DUMP_DIR"' EXIT

for table in "${TABLES[@]}"; do
  dump_file="${DUMP_DIR}/${table}_data.sql"

  echo "Dumping ${SCHEMA}.${table}..."
  pg_dump \
    --dbname="$SOURCE_DATABASE_URL" \
    --data-only \
    --table="\"${SCHEMA}\".\"${table}\"" \
    --no-owner \
    --no-privileges \
    --file="$dump_file"

  echo "Restoring ${SCHEMA}.${table} into dev..."
  psql "$DEV_DATABASE_URL" \
    --set ON_ERROR_STOP=on \
    --single-transaction \
    --command="TRUNCATE TABLE \"${SCHEMA}\".\"${table}\" RESTART IDENTITY CASCADE;" \
    --file="$dump_file"

  echo "Copied ${SCHEMA}.${table} into dev."
done
