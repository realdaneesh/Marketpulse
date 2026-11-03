"""Read-only bounded cross-asset research endpoints for the configured profile."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from marketpulse.api.analytics import ResultLimit, database_result
from marketpulse.cross_asset.models import (
    BreakdownEvent,
    CorrelationFrame,
    CrossProcessingStatus,
    LeadLagResponse,
    RegimeFrame,
    RelationshipMatrix,
)

router = APIRouter(prefix="/api/cross-asset", tags=["cross-asset"])
Asset = Literal["BTCUSDT", "ETHUSDT", "SOLUSDT"]
Pair = Literal["BTCUSDT-ETHUSDT", "BTCUSDT-SOLUSDT", "ETHUSDT-SOLUSDT"]


@router.get("/correlations", response_model=list[CorrelationFrame])
async def correlations(request: Request, limit: ResultLimit = 100) -> list[CorrelationFrame]:
    """Newest-first completed rolling relationships; null coefficients retain readiness."""
    rows = await database_result(
        request.app.state.repository.cross_history(request.app.state.settings, limit)
    )
    return [
        CorrelationFrame(
            profile_id=r.profile_id,
            window_end=r.window_end,
            skipped_intervals=r.skipped_intervals,
            pairs=r.pairs,
            assets=r.assets,
        )
        for r in rows
    ]


@router.get("/matrix", response_model=RelationshipMatrix)
async def matrix(request: Request) -> RelationshipMatrix:
    """Latest relationship matrix/network evidence; diagonals are never synthesized here."""
    return await database_result(
        request.app.state.repository.cross_latest(request.app.state.settings)
    )


@router.get("/breakdowns", response_model=list[BreakdownEvent])
async def breakdowns(
    request: Request, limit: ResultLimit = 100, pair: Annotated[Pair | None, Query()] = None
) -> list[BreakdownEvent]:
    """Stable heuristic relationship-change events; no probability interpretation."""
    return await database_result(
        request.app.state.repository.cross_events(request.app.state.settings, limit, pair)
    )


@router.get("/lead-lag", response_model=LeadLagResponse)
async def lead_lag(
    request: Request,
    leader: Annotated[Asset | None, Query()] = None,
    follower: Annotated[Asset | None, Query()] = None,
) -> LeadLagResponse:
    """A leads B by k: A(t) versus B(t+k); only already-finalized targets are used."""
    if leader is not None and leader == follower:
        raise HTTPException(status_code=422, detail="Leader and follower must be different assets")
    settings = request.app.state.settings
    latest = await database_result(request.app.state.repository.cross_latest(settings))
    snapshot = latest.latest
    analyses = (
        [
            item
            for item in snapshot.lead_lag
            if (leader is None or item.leader == leader)
            and (follower is None or item.follower == follower)
        ]
        if snapshot
        else []
    )
    return LeadLagResponse(
        profile_id=latest.profile_id,
        window_end=snapshot.window_end if snapshot else None,
        window_seconds=settings.analytics.window_seconds,
        status="ready"
        if analyses and all(any(lag.status == "ready" for lag in a.lags) for a in analyses)
        else "insufficient_history",
        analyses=analyses,
        explanation="Exploratory association, multiple-testing risk; "
        "no causation or predictive-performance claim.",
    )


@router.get("/regimes", response_model=list[RegimeFrame])
async def regimes(request: Request, limit: ResultLimit = 100) -> list[RegimeFrame]:
    """Newest-first rule-based descriptions with evidence timestamps and thresholds."""
    rows = await database_result(
        request.app.state.repository.cross_history(request.app.state.settings, limit)
    )
    return [RegimeFrame(profile_id=r.profile_id, regime=r.regime) for r in rows]


@router.get("/regimes/latest", response_model=RegimeFrame | None)
async def latest_regime(request: Request) -> RegimeFrame | None:
    rows = await database_result(
        request.app.state.repository.cross_history(request.app.state.settings, 1)
    )
    return RegimeFrame(profile_id=rows[0].profile_id, regime=rows[0].regime) if rows else None


@router.get("/status", response_model=CrossProcessingStatus)
async def status(request: Request) -> CrossProcessingStatus:
    """Durable progress and source coverage boundary; process heartbeat remains unknown."""
    return await database_result(
        request.app.state.repository.cross_status(request.app.state.settings)
    )
