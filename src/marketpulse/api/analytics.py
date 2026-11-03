"""Read-only analytics routes with bounded queries and explicit readiness models."""

import logging
import sqlite3
from collections.abc import Awaitable
from typing import Annotated, TypeVar

from fastapi import APIRouter, HTTPException, Query, Request

from marketpulse.analytics.models import AnomalyEvent, AnomalySummary, Candle, LatestAnalytics

router = APIRouter(tags=["analytics"])
logger = logging.getLogger(__name__)
SymbolFilter = Annotated[str | None, Query(pattern=r"^[A-Za-z0-9]{2,30}$")]
ResultLimit = Annotated[int, Query(ge=1, le=1000)]
T = TypeVar("T")


async def database_result(operation: Awaitable[T]) -> T:
    try:
        return await operation
    except sqlite3.Error as exc:
        logger.exception("analytics_database_read_failed")
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@router.get("/api/analytics/candles", response_model=list[Candle])
async def candles(
    request: Request, symbol: SymbolFilter = None, limit: ResultLimit = 100
) -> list[Candle]:
    """Finalized windows newest first, including explicit compact missing-interval ranges.

    Monetary values are decimal strings. Null volume in missing intervals means
    unknown market activity. Results use the API's configured analytics profile.
    """
    return await database_result(
        request.app.state.repository.candles(
            request.app.state.settings.analytics.profile_id,
            limit,
            symbol.upper() if symbol else None,
        )
    )


@router.get("/api/analytics/latest", response_model=list[LatestAnalytics])
async def latest(
    request: Request, symbol: SymbolFilter = None, limit: ResultLimit = 100
) -> list[LatestAnalytics]:
    """Latest evaluation per configured symbol, with pending/late counts and warm-up state.

    Empty history yields insufficient_history, not a normal score or anomaly alert.
    A symbol filter can inspect any persisted symbol. The limit caps returned symbols.
    """
    settings = request.app.state.settings
    return await database_result(
        request.app.state.repository.latest(
            settings.analytics.profile_id,
            (symbol.upper(),) if symbol else settings.symbols,
            limit,
        )
    )


@router.get("/api/anomalies/recent", response_model=list[AnomalyEvent])
async def recent(
    request: Request, symbol: SymbolFilter = None, limit: ResultLimit = 100
) -> list[AnomalyEvent]:
    """Combined alerts only; stable identifiers make repeated reads/process runs idempotent."""
    return await database_result(
        request.app.state.repository.events(
            request.app.state.settings.analytics.profile_id,
            limit,
            symbol.upper() if symbol else None,
        )
    )


@router.get("/api/anomalies/summary", response_model=AnomalySummary)
async def summary(
    request: Request, symbol: SymbolFilter = None, limit: ResultLimit = 100
) -> AnomalySummary:
    """Counts and maximum severity within the bounded latest-alert sample, not all time."""
    return await database_result(
        request.app.state.repository.summary(
            request.app.state.settings.analytics.profile_id,
            limit,
            symbol.upper() if symbol else None,
        )
    )
