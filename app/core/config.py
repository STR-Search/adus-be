from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_ENV: str = "development"
    DATABASE_URL: str
    CORS_ORIGINS: str = "*"
    FRED_API_KEY: str = ""

    # Zillow property-details API (Supabase-authenticated)
    ZILLOW_API_BASE: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SERVICE_EMAIL: str = ""
    SERVICE_PASSWORD: str = ""

    # Clerk JWT verification
    CLERK_ISSUER: str = ""  # e.g. https://intent-snapper-24.clerk.accounts.dev
    CLERK_JWKS_URL: str = ""  # e.g. {issuer}/.well-known/jwks.json

    # Sentry error monitoring
    SENTRY_ENABLED: bool = False
    SENTRY_DSN: str = ""

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def async_database_url(self) -> str:
        url = self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
        return f"{url}?ssl=require"


@lru_cache(maxsize=1)
def get_config() -> Config:
    return Config()
