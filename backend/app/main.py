"""
FastAPI application factory.

    uvicorn app.main:app --reload            (development)

Startup: configure logging, then apply database migrations.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, capital
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.migrate import upgrade

log = logging.getLogger("capital_drift")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    upgrade()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Capital Drift Monitor API",
        version="0.1.0",
        description="Checks an HOA's spending against its reserve study: invoice matching, "
        "repair-or-replace warnings, a review queue and a reserve forecast. Synthetic data only.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # pragma: no cover - safety net
        # Log the details server-side; never leak stack traces to clients.
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.get("/api/health", tags=["auth"])
    def health():
        return {"status": "ok"}

    for router in (auth.router, capital.router):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
