"""FastAPI application factory with explicit database lifespan management."""

import logging
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel

from marketpulse.api.analytics import router as analytics_router
from marketpulse.api.cross_asset import router as cross_router
from marketpulse.api.research import router as research_router
from marketpulse.config import Settings
from marketpulse.logging import configure_logging
from marketpulse.models import Trade
from marketpulse.research.repository import ResearchRepository

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str
    database: str
    ingestion: str = "separate_process_not_monitored"


class SymbolsResponse(BaseModel):
    exchange: str = "binance"
    symbols: tuple[str, ...]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an API; collection is deliberately a separate process."""
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        listener = configure_logging(config.log_level)
        try:
            async with ResearchRepository(config.database_path) as repository:
                app.state.repository = repository
                app.state.settings = config
                yield
        finally:
            listener.stop()

    app = FastAPI(title="MarketPulse", version="0.1.0", lifespan=lifespan)
    app.include_router(analytics_router)
    app.include_router(cross_router)
    app.include_router(research_router)

    @app.get("/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        """Check API database access; this does not assert exchange connectivity."""
        try:
            await request.app.state.repository.ping()
        except sqlite3.Error as exc:
            logger.exception("database_health_failed")
            raise HTTPException(status_code=503, detail="Database unavailable") from exc
        return HealthResponse(status="ok", database="ok")

    @app.get("/api/trades/recent", response_model=list[Trade])
    async def recent_trades(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        symbol: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9]{2,30}$")] = None,
    ) -> list[Trade]:
        """Return committed trades newest first; decimals serialize as strings."""
        try:
            return await request.app.state.repository.recent(
                limit=limit,
                symbol=symbol.upper() if symbol else None,
            )
        except sqlite3.Error as exc:
            logger.exception("database_read_failed")
            raise HTTPException(status_code=503, detail="Database unavailable") from exc

    @app.get("/api/market/symbols", response_model=SymbolsResponse)
    async def symbols() -> SymbolsResponse:
        """Return configured subscriptions, not a claim about active connectivity."""
        return SymbolsResponse(symbols=config.symbols)

    return app
