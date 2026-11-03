"""Documented API and persistence models for analytical evidence and availability."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from marketpulse.analytics.config import DetectorName

Quality = Literal["observed", "partial_start", "data_gap", "missing"]
Status = Literal[
    "ready",
    "insufficient_history",
    "incomplete_window",
    "insufficient_activity",
    "unavailable_metric",
]


class AnalyticsModel(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)


class Candle(AnalyticsModel):
    """A finalized event-time window, or a compact range of unknown missing intervals.

    'observed' means eligible under the watermark/continuity policy, not certified
    complete exchange coverage. Missing volumes are null rather than fabricated zeroes.
    """

    symbol: str
    window_start: AwareDatetime
    window_end: AwareDatetime
    window_seconds: int
    quality: Quality
    missing_intervals: int = 0
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    base_volume: Decimal | None = None
    quote_volume: Decimal | None = None
    trade_count: int = 0
    aggressive_buy_volume: Decimal | None = None
    aggressive_sell_volume: Decimal | None = None
    vwap: Decimal | None = None
    log_return: float | None = None
    realized_volatility: float | None = None
    signed_imbalance: float | None = None
    first_trade_id: int | None = None
    last_trade_id: int | None = None
    completeness_note: str


class DetectorResult(AnalyticsModel):
    symbol: str
    window_start: AwareDatetime
    window_end: AwareDatetime
    detector: DetectorName
    status: Status
    observed_metric: float | None
    baseline_metric: float | None = None
    baseline_mad: float | None = None
    effective_scale: float | None = None
    history_count: int = 0
    anomaly_score: float | None = None
    threshold: float
    is_anomaly: bool = False
    explanation: str


class Contribution(AnalyticsModel):
    detector: DetectorName
    status: Status
    weight: float
    points: float | None = Field(default=None, ge=0, le=100)


class RiskAssessment(AnalyticsModel):
    """Heuristic evidence score, never a calibrated forecast or probability."""

    status: Literal["ready", "insufficient_history", "unavailable"]
    score: float | None = Field(default=None, ge=0, le=100)
    alert_threshold: float
    is_alert: bool = False
    contributions: list[Contribution]
    explanation: str


class Evaluation(AnalyticsModel):
    candle: Candle
    detectors: list[DetectorResult]
    risk: RiskAssessment


class AnomalyEvent(AnalyticsModel):
    id: str
    profile_id: str
    symbol: str
    window_start: AwareDatetime
    window_end: AwareDatetime
    risk: RiskAssessment


class LatestAnalytics(AnalyticsModel):
    profile_id: str
    symbol: str
    status: Literal["ready", "insufficient_history", "unavailable"]
    max_event_time: datetime | None = None
    finalized_through: datetime | None = None
    pending_trades: int = 0
    late_trades: int = 0
    evaluation: Evaluation | None = None
    explanation: str


class AnomalySummary(AnalyticsModel):
    """Summary of a bounded sample of recent combined alerts, not an all-time total."""

    profile_id: str
    sample_limit: int
    returned_events: int
    by_symbol: dict[str, int]
    max_score: float | None
    latest_window_end: datetime | None
