"""Explicit evidence, sample support and unavailable-value API contracts."""

from typing import Literal

from pydantic import AwareDatetime, Field

from marketpulse.analytics.models import AnalyticsModel

Readiness = Literal[
    "ready", "insufficient_history", "insufficient_coverage", "zero_variance", "current_ineligible"
]


class PairStatistic(AnalyticsModel):
    asset_a: str
    asset_b: str
    status: Readiness
    coefficient: float | None = Field(default=None, ge=-1, le=1)
    sample_count: int
    expected_count: int
    coverage: float = Field(ge=0, le=1)
    change: float | None = None
    explanation: str


class AssetStatistic(AnalyticsModel):
    symbol: str
    eligible_returns: int
    eligible_candles: int
    expected_count: int
    coverage: float
    return_volatility: float | None = None
    current_return: float | None = None
    volatility_baseline: float | None = None
    baseline_count: int = 0
    elevated_volatility: bool = False


class Breakdown(AnalyticsModel):
    asset_a: str
    asset_b: str
    status: Literal["ready", "insufficient_history", "unavailable"]
    baseline_count: int
    baseline_median: float | None = None
    baseline_mad: float | None = None
    effective_scale: float | None = None
    deviation_score: float | None = None
    change_from_baseline: float | None = None
    direction: Literal["strengthening", "weakening", "unchanged", "unavailable"]
    is_event: bool = False
    explanation: str


class LagStatistic(PairStatistic):
    lag: int


class OutOfSample(AnalyticsModel):
    status: Literal["disabled", "insufficient_history", "ready"]
    split_time: AwareDatetime | None = None
    selected_lag: int | None = None
    train_coefficient: float | None = None
    test_coefficient: float | None = None
    train_count: int = 0
    test_count: int = 0
    train_coverage: float | None = None
    test_coverage: float | None = None
    explanation: str


class LeadLag(AnalyticsModel):
    leader: str
    follower: str
    lags: list[LagStatistic]
    exploratory_selected_lag: int | None = None
    out_of_sample: OutOfSample
    explanation: str


class Regime(AnalyticsModel):
    label: Literal[
        "insufficient_data",
        "normal_observed_conditions",
        "elevated_volatility",
        "high_synchronization",
        "correlation_breakdown",
        "mixed_or_unstable",
    ]
    data_quality: Literal["eligible", "insufficient", "incomplete"]
    evidence_time: AwareDatetime
    ready_pairs: int
    elevated_assets: list[str]
    breakdown_pairs: list[str]
    mean_correlation: float | None = None
    thresholds: dict[str, float]
    explanation: str


class CrossSnapshot(AnalyticsModel):
    id: str
    profile_id: str
    source_profile_id: str
    window_end: AwareDatetime
    window_seconds: int
    lookback: int
    skipped_intervals: int = 0
    status: Literal["ready", "insufficient_history"]
    assets: list[AssetStatistic]
    pairs: list[PairStatistic]
    breakdowns: list[Breakdown]
    lead_lag: list[LeadLag]
    regime: Regime
    explanation: str


class BreakdownEvent(AnalyticsModel):
    id: str
    profile_id: str
    window_end: AwareDatetime
    relationship: PairStatistic
    breakdown: Breakdown


class RelationshipMatrix(AnalyticsModel):
    profile_id: str
    source_profile_id: str
    symbols: list[str]
    status: Literal["ready", "insufficient_history"]
    latest: CrossSnapshot | None = None
    explanation: str


class SourceProgress(AnalyticsModel):
    symbol: str
    max_event_time: AwareDatetime | None
    finalized_through: AwareDatetime | None
    pending_trades: int
    late_trades: int


class CrossProcessingStatus(AnalyticsModel):
    profile_id: str
    source_profile_id: str
    state: Literal["not_started", "waiting_for_sources", "catching_up", "caught_up"]
    processed_through: AwareDatetime | None
    safe_through: AwareDatetime | None
    remaining_intervals: int
    snapshots: int
    last_completed_at: AwareDatetime | None
    source_unstaged_trades: int
    sources: list[SourceProgress]
    database_inside_onedrive: bool
    worker_connectivity: Literal["unknown"] = "unknown"
    explanation: str


class CorrelationFrame(AnalyticsModel):
    profile_id: str
    window_end: AwareDatetime
    skipped_intervals: int
    pairs: list[PairStatistic]
    assets: list[AssetStatistic]


class LeadLagResponse(AnalyticsModel):
    profile_id: str
    window_end: AwareDatetime | None
    window_seconds: int
    status: Literal["ready", "insufficient_history"]
    analyses: list[LeadLag]
    explanation: str


class RegimeFrame(AnalyticsModel):
    profile_id: str
    regime: Regime
