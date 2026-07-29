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
- `app/middleware/` — auth. Do not reorganize.
- `app/dependencies.py` — shared FastAPI dependencies (DB session, auth guards)

## Database Rules
- Managed schemas: `markets`, `iron_bank`, `users`, and `reference`
- `public` schema is owned by another org — never touch it
- Alembic version table lives in `markets` schema
- Four Alembic branches: `markets`, `iron_bank`, `users`, and `reference`

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
