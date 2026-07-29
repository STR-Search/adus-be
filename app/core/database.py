from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_config
from app.core.logger import logger

config = get_config()

engine = create_async_engine(config.async_database_url, echo=False)
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
