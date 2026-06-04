import app.core.logger  # noqa: F401 — triggers logging config at startup

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_config
from app.external_api.router import router as external_api_router
from app.iron_bank.router import router as iron_bank_router
from app.markets.router import router as markets_router
from app.zillow.router import router as zillow_router
from app.middleware.auth import AuthMiddleware


def create_app() -> FastAPI:
    config = get_config()

    application = FastAPI(
        title="ADUS BE",
        version="0.1.0",
        docs_url=None if config.is_production else "/docs",
        redoc_url=None if config.is_production else "/redoc",
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

    return application
