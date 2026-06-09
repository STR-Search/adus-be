#!/bin/bash
set -e

IRON_BANK_BASE="b2673e068337"

echo ">> Downgrading iron_bank to base (drops tables)..."
uv run alembic downgrade iron_bank@base

echo ">> Deleting old iron_bank tables migration file..."
find migrations/versions -name "*.py" | xargs grep -l "down_revision.*$IRON_BANK_BASE" 2>/dev/null | xargs rm -f

echo ">> Restoring iron_bank branch base revision..."
uv run alembic upgrade $IRON_BANK_BASE

echo ">> Regenerating migration..."
uv run alembic revision --autogenerate --head iron_bank@head -m "init_iron_bank_tables"

echo ">> Applying migration..."
uv run alembic upgrade heads

echo "Done."
