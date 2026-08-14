from collections.abc import AsyncGenerator
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import get_config
from app.core.logger import logger

config = get_config()

# We connect through Supabase's *transaction* pooler (PgBouncer, port 6543)
# because the session pooler runs out of connections under our load. Transaction
# mode hands a different backend to each statement, which breaks asyncpg's
# default use of server-side prepared statements — hence:
#   - NullPool: PgBouncer owns pooling; a second pool on our side would pin
#     client connections it can hand out to nobody.
#   - prepared_statement_cache_size=0: a cached statement's backend is gone by
#     the next checkout.
#   - prepared_statement_name_func: asyncpg's default names are sequential
#     (__asyncpg_stmt_1__), so two clients on one backend collide.
# See SQLAlchemy's asyncpg dialect docs, "Prepared Statement Name with PGBouncer".
engine = create_async_engine(
    config.async_database_url,
    echo=False,
    poolclass=NullPool,
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
