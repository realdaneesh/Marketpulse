"""Independent robust, upper-tail detectors using strictly preceding windows."""

import math
from collections.abc import Sequence
from statistics import median

from marketpulse.analytics.config import DETECTORS, AnalyticsConfig, DetectorName
from marketpulse.analytics.models import Candle, DetectorResult


def robust_z_score(
    value: float,
    history: Sequence[float],
    absolute_floor: float = 1e-6,
    relative_floor: float = 0.01,
) -> tuple[float, float, float, float]:
    """Return signed capped Z, median, MAD, and scale.

    Scale=max(1.4826*MAD, |median|*relative_floor, absolute_floor). Floors avoid
    infinite scores for constant baselines. The signed score is capped to +/-100.
    """
    if (
        not history
        or not all(math.isfinite(x) for x in [value, *history])
        or not math.isfinite(absolute_floor)
        or absolute_floor <= 0
        or not math.isfinite(relative_floor)
        or relative_floor <= 0
    ):
        raise ValueError("finite observations and positive scale floors required")
    center = float(median(history))
    mad = float(median([abs(x - center) for x in history]))
    scale = max(1.4826 * mad, abs(center) * relative_floor, absolute_floor)
    if not all(math.isfinite(x) for x in (center, mad, scale)):
        raise ValueError("baseline exceeds floating-point statistical range")
    score = max(-100.0, min(100.0, (value - center) / scale))
    return score, center, mad, scale


def metric(candle: Candle, name: DetectorName) -> float | None:
    raw = {
        "volume": candle.quote_volume,
        "volatility": candle.realized_volatility,
        "imbalance": candle.signed_imbalance,
        "price_shock": candle.log_return,
    }[name]
    if raw is None:
        return None
    value = float(raw)
    return value if math.isfinite(value) else None


def activity_ready(candle: Candle, config: AnalyticsConfig) -> bool:
    return (
        candle.trade_count >= config.min_imbalance_trades
        and candle.quote_volume is not None
        and candle.quote_volume >= config.min_imbalance_quote_volume
    )


def evaluate_detector(
    name: DetectorName,
    candle: Candle,
    history: Sequence[Candle],
    config: AnalyticsConfig,
) -> DetectorResult:
    """Evaluate independently, defensively discarding current/future/other-symbol data."""
    value = metric(candle, name)
    common = dict(
        symbol=candle.symbol,
        window_start=candle.window_start,
        window_end=candle.window_end,
        detector=name,
        observed_metric=value,
        threshold=config.thresholds[name],
    )
    # A gap breaks the baseline run. Do not silently search further back to fill it.
    prior = sorted(
        {
            item.window_start: item
            for item in history
            if item.symbol == candle.symbol
            and item.window_seconds == candle.window_seconds
            and item.window_end <= candle.window_start
            and item.window_start < candle.window_start
        }.values(),
        key=lambda item: item.window_start,
    )[-config.history_size :]
    contiguous: list[Candle] = []
    expected_end = candle.window_start
    for item in reversed(prior):
        if item.quality != "observed" or item.window_end != expected_end:
            break
        contiguous.append(item)
        expected_end = item.window_start
    baseline = [
        metric(item, name)
        for item in contiguous
        if name != "imbalance" or activity_ready(item, config)
    ]
    numbers = [
        abs(x) if name in ("imbalance", "price_shock") else x for x in baseline if x is not None
    ]
    common["history_count"] = len(numbers)
    if candle.quality == "partial_start":
        return DetectorResult(
            **common,
            status="insufficient_history",
            explanation=(
                "First window has unknown starting coverage; cannot seed a baseline. No alert."
            ),
        )
    if candle.quality != "observed":
        return DetectorResult(
            **common, status="incomplete_window", explanation=candle.completeness_note
        )
    if len(numbers) < config.min_history:
        return DetectorResult(
            **common,
            status="insufficient_history",
            explanation=(
                f"{name}: {len(numbers)}/{config.min_history} eligible preceding observations; "
                "no alert."
            ),
        )
    if value is None or candle.base_volume is None or candle.base_volume <= 0:
        return DetectorResult(
            **common,
            status="unavailable_metric",
            explanation=(
                f"{name}: current metric unavailable "
                "(zero volume, no adjacent close, or too few trades)."
            ),
        )
    if name == "imbalance" and not activity_ready(candle, config):
        return DetectorResult(
            **common,
            status="insufficient_activity",
            explanation=(
                f"Imbalance needs at least {config.min_imbalance_trades} trades and "
                f"{config.min_imbalance_quote_volume:g} quote notional; "
                "one-sided sparse activity is not alerted."
            ),
        )
    target = abs(value) if name in ("imbalance", "price_shock") else value
    try:
        z, center, mad, scale = robust_z_score(
            target,
            numbers,
            config.scale_floors[name],
            config.relative_scale_floor,
        )
    except ValueError:
        return DetectorResult(
            **common,
            status="unavailable_metric",
            explanation="Baseline exceeds safe floating-point statistical range; no alert.",
        )
    score = max(0.0, z)
    extreme = name != "imbalance" or abs(value) >= config.min_absolute_imbalance
    anomaly = score >= config.thresholds[name] and extreme
    baseline_kind = "absolute-metric " if name in ("imbalance", "price_shock") else ""
    return DetectorResult(
        **common,
        status="ready",
        baseline_metric=center,
        baseline_mad=mad,
        effective_scale=scale,
        anomaly_score=score,
        is_anomaly=anomaly,
        explanation=(
            f"{name}: observed {value:.8g}; {baseline_kind}"
            f"prior median {center:.8g}, MAD {mad:.8g}, effective scale {scale:.8g}; "
            f"upper-tail score {score:.3f} vs threshold {config.thresholds[name]:g} "
            f"using {len(numbers)} preceding observations. "
            + (
                f"Absolute imbalance must also be >= {config.min_absolute_imbalance:g}. "
                if name == "imbalance"
                else ""
            )
            + ("Anomaly detected." if anomaly else "No anomaly detected.")
        ),
    )


def evaluate_detectors(
    candle: Candle, history: Sequence[Candle], config: AnalyticsConfig
) -> list[DetectorResult]:
    return [evaluate_detector(name, candle, history, config) for name in DETECTORS]
