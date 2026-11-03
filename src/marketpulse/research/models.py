"""Versioned research contracts: descriptive evidence is never labeled prediction."""

import hashlib
import json
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ResearchConfig(Model):
    algorithm_version: Literal["research-v1"] = "research-v1"
    max_intervals: int = Field(default=10080, ge=100, le=10080)
    initialization: int = Field(default=30, ge=10, le=300)
    allowance: float = Field(default=0.5, gt=0)
    threshold: float = Field(default=8, gt=0)
    clip: float = Field(default=8, ge=1, le=20)
    minimum_effect: float = Field(default=1.5, gt=0)
    persistence: int = Field(default=3, ge=2, le=10)
    max_lag: int = Field(default=3, ge=1, le=10)
    block_length: int = Field(default=120, ge=20, le=1000)
    minimum_blocks: int = Field(default=8, ge=8, le=50)
    minimum_episodes: int = Field(default=10, ge=10)
    minimum_controls: int = Field(default=30, ge=30)
    resamples: int = Field(default=199, ge=99, le=999)
    seed: int = Field(default=1729, ge=0)
    alpha: float = Field(default=0.05, gt=0, le=0.1)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def identity(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Experiment(Model):
    id: str
    profile_id: str
    source_profile_id: str
    cross_profile_id: str | None
    algorithm_version: str
    fingerprint: str
    start: AwareDatetime
    end: AwareDatetime
    created_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    state: Literal["pending", "running", "complete", "failed"]
    cursor: int
    total: int
    discrepancies: int = 0
    error: str | None = None
    config: ResearchConfig
    embargo_intervals: int
    sensitivity: dict[str, int] = Field(default_factory=dict)
    explanation: str = "Observational replay, not independent detector validation."


class Metric(Model):
    detector: str
    entity: str
    segment: str
    evaluated: int
    eligible: int
    alerts: int
    frequency: float | None
    warmup_excluded: int
    coverage_excluded: int
    expected_intervals: int
    eligible_coverage: float
    episodes: int
    episode_durations_seconds: list[int]
    score_histogram: list[int]
    overlap: dict[str, int]
    explanation: str = "Unlabeled alert frequency is not a false-positive rate."


class ChangePoint(Model):
    id: str
    experiment_id: str
    entity: str
    feature: str
    segment: str
    start: AwareDatetime
    end: AwareDatetime
    baseline: float
    scale: float
    effect: float
    cumulative_score: float
    threshold: float
    observations: int
    direction: Literal["increase", "decrease"]
    production_alert_nearby: bool
    evidence: list[str]
    explanation: str


class SequenceResult(Model):
    leader: str
    follower: str
    segment: str
    status: Literal["insufficient_data", "exploratory", "held_out_association"]
    lag_intervals: int
    eligible_intervals: int
    expected_intervals: int
    coverage: float
    blocks: int
    leader_episodes: int
    follower_episodes: int
    opportunities: int
    following_events: int
    control_opportunities: int
    control_events: int
    simultaneous: int
    conditional_rate: float | None
    baseline_rate: float | None
    lift: float | None
    effect: float | None
    interval: tuple[float, float] | None = None
    p_value: float | None = None
    adjusted_p: float | None = None
    selected_on_training: bool = False
    explanation: str


class Discovery(Model):
    id: str
    experiment_id: str
    type: str
    assets: list[str]
    start: AwareDatetime
    end: AwareDatetime
    observations: int
    baseline: float | None
    effect: float
    statistical_readiness: Literal["descriptive_only", "assumption_dependent_holdout"]
    coverage: float
    method: str
    config_version: str
    validation: Literal["exploratory", "held_out_association"]
    evidence: list[str]
    limitations: list[str]
    explanation: str


class ResearchStatus(Model):
    state: Literal["schema_not_migrated", "not_started", "available"]
    schema_version: int
    experiments: int
    latest: Experiment | None = None
    worker_connectivity: Literal["unknown"] = "unknown"
    explanation: str


class Results(Model):
    metrics: list[Metric]
    change_points: list[ChangePoint]
    sequences: list[SequenceResult]
    discoveries: list[Discovery]
    sensitivity: dict[str, int]
