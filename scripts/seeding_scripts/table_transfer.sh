#!/usr/bin/env bash

# Usage (run from the repository root):
#   export SOURCE_DATABASE_URL='postgresql://postgres.<source-ref>:<password>@<pooler-host>:5432/postgres'
#   export DEV_DATABASE_URL='postgresql://postgres.<dev-ref>:<password>@<pooler-host>:5432/postgres'
#   PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH" \
#     ./scripts/seeding_scripts/table_transfer.sh

set -euo pipefail

SCHEMA="zillow"

# Add tables in dependency order: referenced/parent tables first.
TABLES=(
  "scheduled_listings"
  "scheduled_listing_details"
)

DUMP_DIR="$(mktemp -d)"
trap 'rm -rf "$DUMP_DIR"' EXIT

for table in "${TABLES[@]}"; do
  if [[ ! "$table" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
    echo "Invalid table name: $table" >&2
    exit 1
  fi

  dump_file="${DUMP_DIR}/${table}_data.sql"

  echo "Dumping ${SCHEMA}.${table}..."
  pg_dump \
    --dbname="$SOURCE_DATABASE_URL" \
    --data-only \
    --table="${SCHEMA}.${table}" \
    --no-owner \
    --no-privileges \
    --file="$dump_file"

  echo "Restoring ${SCHEMA}.${table} into dev..."
  psql "$DEV_DATABASE_URL" \
    --set ON_ERROR_STOP=on \
    --single-transaction \
    --command="TRUNCATE TABLE ${SCHEMA}.${table} RESTART IDENTITY CASCADE;" \
    --file="$dump_file"

  echo "Copied ${SCHEMA}.${table} into dev."
done
