#!/usr/bin/env bash

# Drop and recreate whole schemas in dev from the source database.
#
# Unlike table_transfer.sh (which only copies rows into tables that already
# exist), this rebuilds the schemas themselves: tables, columns, constraints,
# indexes, sequences, views, functions, enums — plus the data by default.
#
# Usage (run from the repository root):
#   export SOURCE_DATABASE_URL=postgresql://postgres.<source-ref>:<password>@<pooler-host>:5432/postgres
#   export DEV_DATABASE_URL=postgresql://postgres.<dev-ref>:<password>@<pooler-host>:5432/postgres
#   PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH" \
#     ./scripts/seeding_scripts/schema_transfer.sh [options]
#
# Options:
#   --schemas a,b,c   Override the schema list (default: the SCHEMAS array below)
#   --schema-only     Recreate structure only, no rows
#   --keep-dump PATH  Write the dump to PATH instead of a temp dir (for review)
#   --yes             Skip the interactive confirmation
#
# Notes:
#   * DROP SCHEMA ... CASCADE also drops objects *outside* these schemas that
#     depend on them (e.g. a view or FK in another schema). That is why this
#     script refuses to run against anything but an explicitly-provided dev URL.
#     In particular, a view or FK in `public` or `users` that points at these
#     schemas is dropped and NOT restored, since those schemas are not dumped.
#     The run is one transaction, so a failed restore rolls the drops back.
#   * `markets.alembic_version` comes across with the markets schema, so dev's
#     migration state ends up matching source. Run `uv run alembic upgrade heads`
#     afterwards if your branch has newer migrations.
#   * Use a session-mode pooler port or the direct DB host. pg_dump/pg_restore
#     do not work through a transaction-mode pooler.
#   * The `public` schema is owned by another org — never add it to SCHEMAS.
#     Dropping it would also destroy the extensions and role grants that live
#     there, which a --schema=public dump does not recreate.

set -euo pipefail

# Schemas to drop and recreate.
SCHEMAS=(
  "markets"
  "iron_bank"
  "reference"
  "zillow"
)

SCHEMA_ONLY=false
ASSUME_YES=false
KEEP_DUMP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --schemas)
      IFS=',' read -r -a SCHEMAS <<< "${2:?--schemas needs a comma-separated list}"
      shift 2
      ;;
    --schema-only)
      SCHEMA_ONLY=true
      shift
      ;;
    --keep-dump)
      KEEP_DUMP="${2:?--keep-dump needs a path}"
      shift 2
      ;;
    --yes|-y)
      ASSUME_YES=true
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

: "${SOURCE_DATABASE_URL:?SOURCE_DATABASE_URL is not set}"
: "${DEV_DATABASE_URL:?DEV_DATABASE_URL is not set}"

if [[ "$SOURCE_DATABASE_URL" == "$DEV_DATABASE_URL" ]]; then
  echo "SOURCE_DATABASE_URL and DEV_DATABASE_URL are identical — refusing to run." >&2
  exit 1
fi

if [[ ${#SCHEMAS[@]} -eq 0 ]]; then
  echo "No schemas selected." >&2
  exit 1
fi

DUMP_ARGS=()
if [[ "$SCHEMA_ONLY" == true ]]; then
  DUMP_ARGS+=(--schema-only)
fi

DROP_SQL=""
SCHEMA_LIST_SQL=""
for schema in "${SCHEMAS[@]}"; do
  if [[ ! "$schema" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
    echo "Invalid schema name: $schema" >&2
    exit 1
  fi
  if [[ "$schema" == "public" ]]; then
    echo "Refusing to touch the public schema." >&2
    exit 1
  fi
  DUMP_ARGS+=(--schema="$schema")
  DROP_SQL+="DROP SCHEMA IF EXISTS ${schema} CASCADE;"
  [[ -n "$SCHEMA_LIST_SQL" ]] && SCHEMA_LIST_SQL+=","
  SCHEMA_LIST_SQL+="'${schema}'"
done

# Show which database is about to be wiped, without leaking the password.
DEV_TARGET="$(psql "$DEV_DATABASE_URL" --tuples-only --no-align \
  --command="SELECT current_user || '@' || coalesce(host(inet_server_addr()), 'local') || '/' || current_database();")"

echo "Source : (SOURCE_DATABASE_URL)"
echo "Target : ${DEV_TARGET}"
echo "Schemas: ${SCHEMAS[*]}"
if [[ "$SCHEMA_ONLY" == true ]]; then
  echo "Mode   : structure only"
else
  echo "Mode   : structure + data"
fi

# Preflight: list foreign keys that cross the boundary of the selected set.
#
#   outbound (selected -> not selected): the restore re-adds these constraints
#     and validates them against the rows already in dev. If source has rows
#     pointing at parent rows dev does not have, ADD CONSTRAINT fails and the
#     whole transaction rolls back. Fix by adding the parent schema to
#     --schemas, syncing the parent rows first, or using --schema-only.
#   inbound (not selected -> selected): DROP SCHEMA CASCADE removes these
#     constraints and they are NOT restored, because their own table is not in
#     the dump. Recreate them by hand afterwards, or widen --schemas.
CROSS_FK_SQL="
SELECT DISTINCT
  CASE WHEN child_ns.nspname IN (${SCHEMA_LIST_SQL}) THEN 'outbound' ELSE 'inbound' END,
  child_ns.nspname || '.' || child.relname || ' -> '
    || parent_ns.nspname || '.' || parent.relname || '  (' || c.conname || ')'
FROM pg_constraint c
JOIN pg_class child ON child.oid = c.conrelid
JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
JOIN pg_class parent ON parent.oid = c.confrelid
JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
WHERE c.contype = 'f'
  AND (child_ns.nspname IN (${SCHEMA_LIST_SQL})) <> (parent_ns.nspname IN (${SCHEMA_LIST_SQL}))
ORDER BY 1, 2;
"

cross_fks="$(psql "$SOURCE_DATABASE_URL" --tuples-only --no-align --field-separator=' | ' \
  --command="$CROSS_FK_SQL")"

if [[ -n "$cross_fks" ]]; then
  echo
  echo "Cross-schema foreign keys (source catalog):"
  while IFS= read -r line; do echo "  $line"; done <<< "$cross_fks"
  echo "  outbound = validated on restore against dev's existing rows."
  echo "  inbound  = dropped by CASCADE and not restored."
fi
echo

if [[ "$ASSUME_YES" != true ]]; then
  read -r -p "This will DROP those schemas in the target. Type 'yes' to continue: " reply
  [[ "$reply" == "yes" ]] || { echo "Aborted."; exit 1; }
fi

if [[ -n "$KEEP_DUMP" ]]; then
  dump_file="$KEEP_DUMP"
else
  DUMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$DUMP_DIR"' EXIT
  dump_file="${DUMP_DIR}/schema_transfer.sql"
fi

echo "Dumping ${SCHEMAS[*]} from source..."
# One pg_dump call for all schemas so pg_dump resolves cross-schema
# dependencies and emits the objects in a restorable order.
pg_dump \
  --dbname="$SOURCE_DATABASE_URL" \
  "${DUMP_ARGS[@]}" \
  --no-owner \
  --no-privileges \
  --no-publications \
  --no-subscriptions \
  --no-security-labels \
  --quote-all-identifiers \
  --file="$dump_file"

echo "Dropping and recreating ${SCHEMAS[*]} in dev..."
psql "$DEV_DATABASE_URL" \
  --set ON_ERROR_STOP=on \
  --single-transaction \
  --quiet \
  --command="$DROP_SQL" \
  --file="$dump_file"

echo "Done. Recreated: ${SCHEMAS[*]}"
if [[ -n "$KEEP_DUMP" ]]; then
  echo "Dump kept at: $KEEP_DUMP"
fi
