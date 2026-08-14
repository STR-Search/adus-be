from collections.abc import AsyncGenerator
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_config
from app.core.logger import logger

config = get_config()

# DATABASE_URL must point at Supabase's *transaction* pooler (Supavisor, port
# 6543), not the session pooler on 5432. In session mode every client connection
# reserves a Postgres backend for as long as it is held, so this pool alone could
# exhaust the branch's backend allowance while sitting idle. Transaction mode
# only borrows a backend for the duration of a transaction, which is what makes a
# normal client-side pool safe here.
#
# The cost of transaction mode: consecutive statements on one client connection
# may land on different backends, which breaks asyncpg's use of server-side
# prepared statements. Both connect_args below are required, not tuning —
#   - prepared_statement_cache_size=0: a cached statement's backend is gone by
#     the next checkout (InvalidSQLStatementNameError).
#   - prepared_statement_name_func: asyncpg's default names are sequential
#     (__asyncpg_stmt_1__), so two clients multiplexed onto one backend collide
#     (DuplicatePreparedStatementError).
# See SQLAlchemy's asyncpg dialect docs, "Prepared Statement Name with PGBouncer".
#
# pool_pre_ping/pool_recycle guard against handing out a connection Supavisor has
# already reaped, which surfaces as "connection was closed in the middle of
# operation" on the first query after an idle period.
#
# Sizing note: background batch jobs (app/workflows/job_runner.py) draw from this
# same pool and hold a connection for minutes at a time, so max_overflow carries
# headroom for them on top of request traffic.
engine = create_async_engine(
    config.async_database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,
    pool_pre_ping=True,
    connect_args={
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    },
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Max chars kept from statement/params in logs — enough to diagnose, bounded so
# a huge query or bulk parameter set can't flood the log line.
_MAX_LOG_LEN = 2000


def _truncate(value: object) -> str:
    text = str(value)
    return text if len(text) <= _MAX_LOG_LEN else f"{text[:_MAX_LOG_LEN]}… (truncated)"


@event.listens_for(engine.sync_engine, "handle_error")
def _log_db_error(context) -> None:
    """Emit the *original* DBAPI error before SQLAlchemy wraps/propagates it.

    The original exception carries the real Postgres message (e.g.
    "relation ... does not exist"), which SQLAlchemy's wrapper would otherwise
    bury and downstream `str(exc)` capture truncates. Server-side only — this
    never reaches API responses or the browser. We only log and return; the
    exception continues to propagate unchanged.
    """
    if not config.DB_ERROR_LOGGING:
        return
    original = context.original_exception
    logger.error(
        "db.query_error",
        error=_truncate(original),
        error_type=type(original).__name__,
        statement=_truncate(context.statement) if context.statement else None,
        parameters=_truncate(context.parameters) if context.parameters else None,
    )


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
