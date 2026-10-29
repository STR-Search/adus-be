# adus-be

FastAPI backend. Async SQLAlchemy + Alembic on a shared PostgreSQL instance.

## Architecture

Domain-based under `app/`. Each domain owns its models, schemas, services,
repositories, controllers, and router.

### Current Domains
| Domain | Folder | DB Schema |
|---|---|---|
| Market truth tables | `app/markets/` | `markets` |
| Financial data | `app/iron_bank/` | `iron_bank` |
| Third-party APIs | `app/external_api/` | none |

### Shared
- `app/core/` — config, DB engine, logger. Do not reorganize.
- `app/core/reference_data/` — shared, DB-backed enum/reference-data system
  (`reference.enum_options` table). Any domain stores a stable **slug** on its
  tag columns and resolves labels via `ReferenceDataService`. Full layered CRUD
  (repository/service/controller/router) plus `GET/POST/PATCH /reference-data`.
- `app/core/discussions/` — shared comment threads (`discussions` schema).
  Domains link entities to threads via their own link tables (e.g.
  `iron_bank.underwriting_threads`) and call it only through its service; it
  never imports a domain. Design: `docs/underwriting_discussions.md`.
- `app/core/process_log/` — append-only status history (`process_log` schema).
  Domains record transitions of a named flow (e.g. underwriting `deal_status`)
  through `ProcessLogService` only, in the same transaction as the status
  change; subjects are referenced logically (no FK). It never imports a domain.
  Design: `docs/features/process_log/process_log.md`.
- `app/analytics/` — read-only composition layer for `/analytics/*`. Owns no
  tables, models, or migrations. Each domain owns its own analytics queries
  (e.g. `iron_bank/repositories/underwriting_analytics_repository.py` +
  `iron_bank/services/analytics/`); `app/analytics/` holds only the controller,
  router, composed response schemas, and — solely for metrics that need a SQL
  join across domain schemas — its own read-only repositories plus the services
  that shape their results (`app/analytics/services/`). Shared response shapes
  and ordering rules live in `app/core/analytics/`; shared WHERE-clause
  builders (date/numeric ranges) in `app/core/query_filters.py`.
- `app/middleware/` — auth. Do not reorganize.
- `app/dependencies.py` — shared FastAPI dependencies (DB session, auth guards)

## Database Rules
- Managed schemas: `markets`, `iron_bank`, `users`, `reference`, `discussions`, and `process_log`
- `public` schema is owned by another org — never touch it
- Alembic version table lives in `markets` schema
- Six Alembic branches: `markets`, `iron_bank`, `users`, `reference`, `discussions`, and `process_log`

## Auth
- Global guard: `dependencies=[Depends(get_current_user)]` in `app/__init__.py`
  applies to every route (except `/docs`, `/redoc`, `/openapi.json`).
- `get_current_user` (`app/dependencies.py`) accepts two credentials, both
  resolving to a `User`:
  - `X-ADUS-API-KEY: <key>` — API-key auth (CLI / external teams). Checked first.
  - `Authorization: Bearer <jwt>` — Clerk JWT auth (app / browser users).
- API keys are stored hashed (SHA-256) in `users.api_keys`; plaintext is shown
  once at creation. Manage via `POST/GET/DELETE /users/api-keys`, or bootstrap
  one with `uv run python scripts/issue_api_key.py --user-id <id> --name <name>`.

## Commands

```bash
# Dev server
uvicorn main:app --reload

# Run both migration branches
alembic upgrade heads

# New markets migration
alembic revision --autogenerate -m "description"

# New iron_bank migration (once models exist)
alembic revision --autogenerate -m "description"
# Alembic auto-detects the iron_bank branch from the current head

# Check both heads
alembic heads
```

## Model Conventions
- All models inherit from `app.core.database.Base`
- All models use `__table_args__ = {"schema": "markets"}` (or `"iron_bank"` for iron_bank models)
- Routers registered in `app/__init__.py`
- Never import between domains — shared logic goes in `app/core/`
