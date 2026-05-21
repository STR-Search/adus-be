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
- `app/middleware/` — auth. Do not reorganize.
- `app/dependencies.py` — shared FastAPI dependencies (DB session, auth guards)

## Database Rules
- Managed schemas: `markets` and `iron_bank`
- `public` schema is owned by another org — never touch it
- Alembic version table lives in `markets` schema
- Two Alembic branches: `markets` and `iron_bank`

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
