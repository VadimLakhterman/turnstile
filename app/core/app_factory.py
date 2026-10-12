from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import Settings
from app.core.errors import register_error_handlers
from app.core.logging_config import setup_logging
from app.core.middleware import CorrelationIdMiddleware
from app.core.provider import build_lifespan


def create_app(settings: Settings) -> FastAPI:
    setup_logging(settings.LOG_LEVEL)
    app = FastAPI(title="Turnstile", version="0.1.0", lifespan=build_lifespan(settings))
    app.add_middleware(CorrelationIdMiddleware)
    register_error_handlers(app)
    app.include_router(api_router)
    return app
