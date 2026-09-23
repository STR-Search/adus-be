# adus-be

FastAPI backend (async SQLAlchemy + Alembic on PostgreSQL).

## Getting started

### 1. Install uv

This repo uses [uv](https://docs.astral.sh/uv/) for Python, dependencies, and
running commands.

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# or: brew install uv
```

### 2. Create the virtual environment and install dependencies

```bash
uv venv          # creates .venv using the Python version in .python-version (3.12)
uv sync          # installs all dependencies (including dev) from uv.lock
```

You don't need to activate the venv — prefix commands with `uv run` instead.

### 3. Configure environment variables

Copy the example env file:

```bash
cp .env.example .env
```

Then open `.env` and fill in the real credentials:

| Variable | What to put |
|---|---|
| `DATABASE_URL` | Supabase pooler URL in **transaction mode** (port `6543`). Replace `<project-ref>`, `<password>`, and `<region>`. |
| `MIGRATION_DATABASE_URL` | Same pooler in **session mode** (port `5432`). Used by Alembic only; falls back to `DATABASE_URL` if unset. |
| `ZILLOW_API_KEY` | API key for the Zillow data-enrichment service. |
| `CLERK_ISSUER` / `CLERK_JWKS_URL` | Clerk instance used to verify JWTs. |
| `SENTRY_ENABLED` / `SENTRY_DSN` | Leave disabled locally unless you need error reporting. |
| `N8N_WEBHOOK_*` | Leave `*_ENABLED=false` locally. Enabling them triggers real automations. |

### 4. Start the dev server

```bash
uv run uvicorn main:app --reload
```

The API runs at http://localhost:8000. Interactive docs are at
http://localhost:8000/docs.

## Authentication

Every route (except `/docs`, `/redoc`, `/openapi.json`) requires either:

- `X-ADUS-API-KEY: <key>`, or
- `Authorization: Bearer <clerk-jwt>`

To issue yourself a local API key:

```bash
uv run python scripts/issue_api_key.py --user-id <id> --name <name>
```

## Tests

```bash
uv run pytest
```
