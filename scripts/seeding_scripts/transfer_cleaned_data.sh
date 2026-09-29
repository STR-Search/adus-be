#!/usr/bin/env bash

# Usage (run from the repository root):
#   export SOURCE_DATABASE_URL=postgresql://postgres.<source-ref>:<password>@<pooler-host>:5432/postgres
#   export DEV_DATABASE_URL=postgresql://postgres.<dev-ref>:<password>@<pooler-host>:5432/postgres
#   PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH" \
#     ./scripts/seeding_scripts/transfer_cleaned_data.sh [--batch-size 50000] [--resume]

set -euo pipefail

SCHEMA="public"
TABLE="cleaned_data"
BATCH_SIZE=50000
RESUME=false

usage() {
  cat <<'USAGE'
Usage: transfer_cleaned_data.sh [--batch-size N] [--resume]

Stream public.cleaned_data from SOURCE_DATABASE_URL to DEV_DATABASE_URL in
id-ordered batches. Each batch is its own COPY and commits on its own, so a
failure only loses the batch in flight.

  --batch-size N  Rows per batch (default 50000).
  --resume        Keep existing dev rows and continue after the highest id
                  already in dev. Without it, the dev table is truncated
                  (CASCADE) first.

Prerequisites in dev: the table exists, and every referenced
public.processing_executions and markets.market_keys_master row exists.
USAGE
}

fail() {
  echo "Error: $*" >&2
  exit 1
}

while (( $# > 0 )); do
  case "$1" in
    --batch-size)
      [[ $# -ge 2 && "$2" =~ ^[1-9][0-9]*$ ]] || fail "--batch-size requires a positive integer"
      BATCH_SIZE="$2"
      shift 2
      ;;
    --resume) RESUME=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "Unknown argument: $1 (see --help)" ;;
  esac
done

[[ -n "${SOURCE_DATABASE_URL:-}" ]] || fail "Export SOURCE_DATABASE_URL first"
[[ -n "${DEV_DATABASE_URL:-}" ]] || fail "Export DEV_DATABASE_URL first"
[[ "$SOURCE_DATABASE_URL" != "$DEV_DATABASE_URL" ]] || fail "SOURCE and DEV URLs are identical"
command -v psql >/dev/null || fail "psql is required"

QUALIFIED="\"${SCHEMA}\".\"${TABLE}\""

# Scalar query helper: no psqlrc, unaligned, tuples only.
src_q() { psql "$SOURCE_DATABASE_URL" -X -At -v ON_ERROR_STOP=1 -c "$1"; }
dev_q() { psql "$DEV_DATABASE_URL" -X -At -v ON_ERROR_STOP=1 -c "$1"; }

# Use the dev table's column list on both sides so column-order drift between
# the two databases cannot shift values into the wrong columns.
COLUMNS="$(dev_q "
  SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)
  FROM information_schema.columns
  WHERE table_schema = '${SCHEMA}' AND table_name = '${TABLE}'")"
[[ -n "$COLUMNS" ]] || fail "${SCHEMA}.${TABLE} does not exist in dev"

SOURCE_TOTAL="$(src_q "SELECT count(*) FROM ${QUALIFIED}")"
SOURCE_SIZE="$(src_q "SELECT pg_size_pretty(pg_total_relation_size('${QUALIFIED}'))")"
echo "Source ${SCHEMA}.${TABLE}: ${SOURCE_TOTAL} rows, ${SOURCE_SIZE}. Batch size: ${BATCH_SIZE}."

if [[ "$RESUME" == true ]]; then
  LAST_ID="$(dev_q "SELECT coalesce(max(id), 0) FROM ${QUALIFIED}")"
  echo "Resuming after id ${LAST_ID}."
else
  echo "Truncating dev ${SCHEMA}.${TABLE} (CASCADE)..."
  dev_q "TRUNCATE TABLE ${QUALIFIED} RESTART IDENTITY CASCADE" >/dev/null
  LAST_ID=0
fi

batch=0
copied=0
START=$SECONDS
while true; do
  # Upper id of the next batch; an index-only scan on the primary key.
  HI_ID="$(src_q "
    SELECT max(id) FROM (
      SELECT id FROM ${QUALIFIED} WHERE id > ${LAST_ID} ORDER BY id LIMIT ${BATCH_SIZE}
    ) s")"
  [[ -n "$HI_ID" ]] || break

  batch=$((batch + 1))
  batch_start=$SECONDS
  printf 'Batch %d: id (%s, %s] ... ' "$batch" "$LAST_ID" "$HI_ID"

  psql "$SOURCE_DATABASE_URL" -X -v ON_ERROR_STOP=1 \
    -c "\copy (SELECT ${COLUMNS} FROM ${QUALIFIED} WHERE id > ${LAST_ID} AND id <= ${HI_ID} ORDER BY id) TO STDOUT WITH (FORMAT csv)" \
  | psql "$DEV_DATABASE_URL" -X -q -v ON_ERROR_STOP=1 \
    -c "\copy ${QUALIFIED} (${COLUMNS}) FROM STDIN WITH (FORMAT csv)"

  copied="$(dev_q "SELECT count(*) FROM ${QUALIFIED}")"
  printf 'done in %ds (%s/%s rows in dev)\n' "$((SECONDS - batch_start))" "$copied" "$SOURCE_TOTAL"
  LAST_ID="$HI_ID"
done

# RESTART IDENTITY reset the sequence to 1; move it past the copied ids.
dev_q "SELECT setval(pg_get_serial_sequence('${SCHEMA}.${TABLE}', 'id'),
                     coalesce((SELECT max(id) FROM ${QUALIFIED}), 1))" >/dev/null

copied="$(dev_q "SELECT count(*) FROM ${QUALIFIED}")"
echo "Finished ${batch} batches in $((SECONDS - START))s. Dev rows: ${copied}, source rows: ${SOURCE_TOTAL}."
