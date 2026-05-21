import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import pool, text

from alembic import context

from app.core.config import get_config
from app.core.database import Base
import app.markets.models   # noqa: F401
import app.iron_bank.models # noqa: F401

TARGET_SCHEMAS = ["markets", "iron_bank"]

config = context.config
config.set_main_option("sqlalchemy.url", get_config().async_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name in TARGET_SCHEMAS
    return True


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        return object.schema in TARGET_SCHEMAS
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
        version_table_schema="markets",
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    for schema in TARGET_SCHEMAS:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
        version_table_schema="markets",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(
        get_config().async_database_url,
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        async with connection.begin():
            await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()