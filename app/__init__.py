import sentry_sdk

import app.core.logger  # noqa: F401 — triggers logging config at startup

from app.core.logger import logger

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_config
from app.dependencies import get_current_user
from app.external_api.router import router as external_api_router
from app.iron_bank.router import router as iron_bank_router
from app.markets.router import router as markets_router
from app.users.router import router as users_router
from app.zillow.router import router as zillow_router
from app.middleware.auth import AuthMiddleware


def create_app() -> FastAPI:
    config = get_config()

    if config.SENTRY_ENABLED:
        if config.SENTRY_DSN:
            sentry_sdk.init(
                dsn=config.SENTRY_DSN,
                environment=config.APP_ENV,
                send_default_pii=False,
            )
            logger.info("SENTRY Connected")
        else:
            logger.warning(
                "SENTRY_ENABLED is true but SENTRY_DSN is empty — Sentry disabled"
            )

    application = FastAPI(
        title="ADUS BE",
        version="0.1.0",
        docs_url=None if config.is_production else "/docs",
        redoc_url=None if config.is_production else "/redoc",
        # Global Clerk JWT enforcement. Does not apply to /docs, /redoc,
        # /openapi.json. FastAPI caches the dependency per request, so handlers
        # that also declare get_current_user reuse this result.
        dependencies=[Depends(get_current_user)],
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.add_middleware(AuthMiddleware)

    application.include_router(markets_router)
    application.include_router(iron_bank_router)
    application.include_router(external_api_router)
    application.include_router(zillow_router)
    application.include_router(users_router)

    return application
