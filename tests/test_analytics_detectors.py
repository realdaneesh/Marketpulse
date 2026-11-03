from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from marketpulse.analytics.config import AnalyticsConfig
from marketpulse.analytics.detectors import evaluate_detector, evaluate_detectors, robust_z_score
from marketpulse.analytics.models import Candle
from marketpulse.analytics.scoring import combine_results


def candle(index, **updates):
    start = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=index)
    return Candle(
        symbol="BTCUSDT",
        window_start=start,
        window_end=start + timedelta(minutes=1),
        window_seconds=60,
        quality="observed",
        base_volume=Decimal(10),
        quote_volume=Decimal(1000),
        trade_count=100,
        realized_volatility=0.01,
        log_return=0.001,
        signed_imbalance=0.1,
        completeness_note="Synthetic deterministic fixture",
    ).model_copy(update=updates)


@pytest.fixture
def policy():
    return AnalyticsConfig(min_history=3, history_size=5)


def test_robust_z_known_value_and_zero_mad():
    score, center, mad, scale = robust_z_score(10, [1, 2, 3, 4, 5])
    assert (center, mad, scale) == (3, 1, 1.4826)
    assert score == pytest.approx(7 / 1.4826)
    assert robust_z_score(0, [0, 0, 0])[0] == 0
    assert robust_z_score(10, [0, 0, 0])[0] == 100
    assert robust_z_score(100, [100, 100, 100])[0] == 0
    with pytest.raises(ValueError):
        robust_z_score(float("nan"), [0, 1])


@pytest.mark.parametrize(
    "name,updates",
    [
        ("volume", {"quote_volume": Decimal(100000)}),
        ("volatility", {"realized_volatility": 1.0}),
        ("imbalance", {"signed_imbalance": -0.99}),
        ("price_shock", {"log_return": -0.5}),
    ],
)
def test_four_independent_detectors(policy, name, updates):
    result = evaluate_detector(name, candle(3, **updates), [candle(i) for i in range(3)], policy)
    assert result.status == "ready" and result.is_anomaly
    assert result.anomaly_score > result.threshold
    assert result.history_count == 3
    assert result.baseline_metric is not None
    assert "preceding observations" in result.explanation


def test_lower_volatility_and_volume_are_not_spikes(policy):
    history = [candle(i) for i in range(3)]
    assert not evaluate_detector(
        "volatility", candle(3, realized_volatility=0), history, policy
    ).is_anomaly
    assert not evaluate_detector(
        "volume", candle(3, quote_volume=Decimal(1)), history, policy
    ).is_anomaly


def test_warmup_no_alert_and_no_future_data_leakage(policy):
    current = candle(3, quote_volume=Decimal(1000000))
    past = [candle(i) for i in range(3)]
    expected = evaluate_detector("volume", current, past, policy)
    polluted = [
        *past,
        current,
        candle(4, quote_volume=Decimal("1e30")),
        candle(0, symbol="ETHUSDT"),
    ]
    assert evaluate_detector("volume", current, polluted, policy) == expected
    result = evaluate_detector("volume", current, past[:2], policy)
    assert result.status == "insufficient_history" and not result.is_anomaly
    assert result.anomaly_score is None


def test_gap_resets_baseline_and_current_incomplete_is_not_scored(policy):
    past = [candle(i) for i in range(3)]
    past[1] = candle(1, quality="missing", quote_volume=None)
    result = evaluate_detector("volume", candle(3), past, policy)
    assert result.status == "insufficient_history" and result.history_count == 1
    # Also detect a missing interval when the caller omitted its marker.
    assert evaluate_detector("volume", candle(3), [candle(0), candle(2)], policy).history_count == 1
    assert (
        evaluate_detector("volume", candle(3, quality="data_gap"), past, policy).status
        == "incomplete_window"
    )


@pytest.mark.parametrize("updates", [{"trade_count": 1}, {"quote_volume": Decimal(1)}])
def test_low_activity_imbalance_is_unavailable(policy, updates):
    result = evaluate_detector(
        "imbalance", candle(3, signed_imbalance=1, **updates), [candle(i) for i in range(3)], policy
    )
    assert result.status == "insufficient_activity" and not result.is_anomaly


def test_zero_volume_is_safe_and_abs_imbalance_floor_applies(policy):
    past = [candle(i, signed_imbalance=0) for i in range(3)]
    result = evaluate_detector("volume", candle(3, base_volume=Decimal(0)), past, policy)
    assert result.status == "unavailable_metric" and not result.is_anomaly
    imbalance = evaluate_detector("imbalance", candle(3, signed_imbalance=0.3), past, policy)
    assert imbalance.anomaly_score > imbalance.threshold
    assert not imbalance.is_anomaly


def test_risk_contributions_and_required_history(policy):
    results = evaluate_detectors(
        candle(
            3,
            quote_volume=Decimal(100000),
            realized_volatility=1,
            log_return=0.5,
            signed_imbalance=1,
        ),
        [candle(i) for i in range(3)],
        policy,
    )
    risk = combine_results(results, policy)
    assert risk.score == 100 and risk.is_alert
    assert [c.points for c in risk.contributions] == [25] * 4
    results[0] = results[0].model_copy(
        update={"status": "insufficient_history", "anomaly_score": None, "is_anomaly": False}
    )
    blocked = combine_results(results, policy)
    assert blocked.score is None and not blocked.is_alert
    assert blocked.status == "insufficient_history"
    assert blocked.contributions[0].points is None
    optional = policy.model_copy(
        update={"required_detectors": ("volatility", "imbalance", "price_shock")}
    )
    assert combine_results(results, optional).score == 75


def test_normal_indicator_contributes_zero_not_null(policy):
    results = evaluate_detectors(candle(3), [candle(i) for i in range(3)], policy)
    risk = combine_results(results, policy)
    assert risk.status == "ready" and risk.score == 0 and not risk.is_alert
    assert all(c.points == 0 for c in risk.contributions)


def test_config_validation_and_profile_stability():
    from pydantic import ValidationError

    assert AnalyticsConfig().profile_id == AnalyticsConfig().profile_id
    assert AnalyticsConfig(window_seconds=30).profile_id != AnalyticsConfig().profile_id
    for values in (
        {"min_history": 100},
        {"weights": {"volume": 1}},
        {"required_detectors": ()},
        {"relative_scale_floor": 0},
        {"allowed_lateness_seconds": -1},
    ):
        with pytest.raises(ValidationError):
            AnalyticsConfig(**values)
