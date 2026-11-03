"""Versioned, bounded research endpoints. No request starts a job or migration."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request

from marketpulse.analytics.models import Candle
from marketpulse.api.analytics import database_result
from marketpulse.cross_asset.models import CrossSnapshot
from marketpulse.research.models import (
    ChangePoint,
    Discovery,
    Experiment,
    Metric,
    Model,
    ResearchStatus,
    SequenceResult,
)

router = APIRouter(prefix="/api/research/v1", tags=["research"])
Key = Annotated[str, Path(pattern="^[a-f0-9]{64}$")]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0, le=100000)]


class Evidence(Model):
    id: str
    kind: Literal["candle", "cross", "change_point"]
    observation: Candle | CrossSnapshot | ChangePoint


@router.get("/status", response_model=ResearchStatus)
async def status(request: Request):
    return await database_result(request.app.state.repository.research_status())


async def available(request: Request):
    if (await database_result(request.app.state.repository.research_status())).schema_version < 4:
        raise HTTPException(
            status_code=503, detail="Research schema not migrated; approval required"
        )
    return request.app.state.repository


@router.get("/experiments", response_model=list[Experiment])
async def experiments(request: Request, limit: Limit = 100, offset: Offset = 0):
    repo = await available(request)
    return await database_result(repo.research_list("experiments", None, limit, offset))


@router.get("/experiments/{experiment_id}", response_model=Experiment)
async def experiment(request: Request, experiment_id: Key):
    repo = await available(request)
    row = await database_result(repo.research_detail("experiments", experiment_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return row


async def experiment_rows(request: Request, key: str, kind: str, limit: int, offset: int):
    await experiment(request, key)
    return await database_result(
        request.app.state.repository.research_list(kind, key, limit, offset)
    )


@router.get("/experiments/{experiment_id}/metrics", response_model=list[Metric])
async def metrics(request: Request, experiment_id: Key, limit: Limit = 100, offset: Offset = 0):
    return await experiment_rows(request, experiment_id, "metrics", limit, offset)


@router.get("/experiments/{experiment_id}/change-points", response_model=list[ChangePoint])
async def changes(request: Request, experiment_id: Key, limit: Limit = 100, offset: Offset = 0):
    return await experiment_rows(request, experiment_id, "change-points", limit, offset)


@router.get("/experiments/{experiment_id}/sequences", response_model=list[SequenceResult])
async def sequences(request: Request, experiment_id: Key, limit: Limit = 100, offset: Offset = 0):
    return await experiment_rows(request, experiment_id, "sequences", limit, offset)


@router.get("/experiments/{experiment_id}/discoveries", response_model=list[Discovery])
async def discoveries(request: Request, experiment_id: Key, limit: Limit = 100, offset: Offset = 0):
    return await experiment_rows(request, experiment_id, "discoveries", limit, offset)


@router.get("/discoveries/{discovery_id}", response_model=Discovery)
async def discovery(request: Request, discovery_id: Key):
    repo = await available(request)
    row = await database_result(repo.research_detail("discoveries", discovery_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Discovery not found")
    return row


@router.get("/discoveries/{discovery_id}/evidence", response_model=list[Evidence])
async def evidence(request: Request, discovery_id: Key):
    repo = await available(request)
    row = await database_result(repo.research_evidence(discovery_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Discovery not found")
    return row
