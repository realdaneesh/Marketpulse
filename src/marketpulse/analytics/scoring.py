"""Transparent fixed-weight anomaly severity, explicitly separate from probability."""

from marketpulse.analytics.config import AnalyticsConfig
from marketpulse.analytics.models import Contribution, DetectorResult, RiskAssessment


def combine_results(results: list[DetectorResult], config: AnalyticsConfig) -> RiskAssessment:
    """Sum weighted clipped threshold excess; unavailable required inputs suppress scores."""
    by_name = {item.detector: item for item in results}
    contributions = []
    total_weight = sum(config.weights.values())
    for name, weight in config.weights.items():
        result = by_name.get(name)
        status = result.status if result else "unavailable_metric"
        points = None
        if result is not None and status == "ready" and result.anomaly_score is not None:
            severity = min(1.0, max(0.0, result.anomaly_score / result.threshold - 1.0))
            points = 100 * (weight / total_weight) * severity if result.is_anomaly else 0.0
        contributions.append(
            Contribution(detector=name, status=status, weight=weight, points=points)
        )
    blocked = [
        c for c in contributions if c.detector in config.required_detectors and c.points is None
    ]
    if blocked:
        status = (
            "insufficient_history"
            if any(c.status == "insufficient_history" for c in blocked)
            else "unavailable"
        )
        return RiskAssessment(
            status=status,
            alert_threshold=config.alert_threshold,
            contributions=contributions,
            explanation="Combined score unavailable; required indicators not ready: "
            + ", ".join(f"{c.detector}={c.status}" for c in blocked)
            + ". No combined alert.",
        )
    score = min(100.0, sum(c.points or 0.0 for c in contributions))
    return RiskAssessment(
        status="ready",
        score=score,
        alert_threshold=config.alert_threshold,
        is_alert=score >= config.alert_threshold,
        contributions=contributions,
        explanation="Fixed-weight sum of clipped threshold excess "
        "(full contribution at 2x threshold). "
        "Unavailable optional indicators retain null contributions; weights are not renormalized. "
        "This is an evidence severity score, not a calibrated probability or price forecast.",
    )
