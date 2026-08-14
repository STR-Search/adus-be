from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_ENV: str = "development"
    # Transaction pooler (port 6543). See app/core/database.py.
    DATABASE_URL: str
    # Alembic's connection, pointing at the SESSION pooler (port 5432) instead.
    # Session mode gives a migration a dedicated backend for the life of the
    # connection, so server-side prepared statements work normally, session-level
    # state (advisory locks, SET) holds, and no pooler transaction timeout can cut
    # a long DDL statement in half. Optional: falls back to DATABASE_URL, which
    # still works but carries those caveats.
    MIGRATION_DATABASE_URL: str = ""
    CORS_ORIGINS: str = "*"
    FRED_API_KEY: str = ""

    # Zillow property-details API (API-key authenticated)
    ZILLOW_API_BASE: str = ""
    ZILLOW_API_KEY: str = ""

    # Clerk JWT verification
    CLERK_ISSUER: str = ""  # e.g. https://intent-snapper-24.clerk.accounts.dev
    CLERK_JWKS_URL: str = ""  # e.g. {issuer}/.well-known/jwks.json

    # Sentry error monitoring
    SENTRY_ENABLED: bool = False
    SENTRY_DSN: str = ""

    # n8n automation webhooks, fired on selected deal-status transitions.
    # Each workflow is independently configurable so it can be tested or
    # disabled without affecting the other.
    N8N_WEBHOOK_PRESENT_TO_CLIENTS_URL: str = ""
    N8N_WEBHOOK_PRESENT_TO_CLIENTS_ENABLED: bool = False
    N8N_WEBHOOK_ANALYST_COMPLETED_URL: str = ""
    N8N_WEBHOOK_ANALYST_COMPLETED_ENABLED: bool = False
    N8N_WEBHOOK_TIMEOUT_SECONDS: int = 10

    # Log the original DBAPI error (message + SQL + params) at the engine
    # boundary. Server-side only; never reaches clients. Safe to leave on in
    # every environment — kept as a flag purely so verbosity is toggleable.
    DB_ERROR_LOGGING: bool = True

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @staticmethod
    def _to_async_url(url: str) -> str:
        """Point a libpq URL at the asyncpg driver and require TLS.

        ``ssl=require`` is only appended when the URL has no query string of its
        own — appending blindly would corrupt one that does (e.g. a connection
        string pasted with ``?sslmode=require`` already on it).
        """
        async_url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return async_url if "?" in async_url else f"{async_url}?ssl=require"

    @property
    def async_database_url(self) -> str:
        return self._to_async_url(self.DATABASE_URL)

    @property
    def async_migration_database_url(self) -> str:
        return self._to_async_url(self.MIGRATION_DATABASE_URL or self.DATABASE_URL)


@lru_cache(maxsize=1)
def get_config() -> Config:
    return Config()
