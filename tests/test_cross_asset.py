"""Deterministic synthetic research tests; no live database or exchange access."""

import math
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from marketpulse.analytics.models import Candle
from marketpulse.cross_asset.alignment import aligned_returns
from marketpulse.cross_asset.config import SYMBOLS, CrossAssetConfig
from marketpulse.cross_asset.engine import classify, evaluate, lead_lag, pair_stat, pearson

START = datetime(2024, 1, 1, tzinfo=UTC)
STEP = timedelta(minutes=1)


def policy(**updates):
    return CrossAssetConfig(
        lookback=8,
        min_pairs=4,
        min_coverage=0.5,
        baseline_windows=5,
        min_baseline=3,
        max_lag=2,
        **updates,
    )


def make_candles(count=30, mode="positive"):
    result = []
    closes = dict.fromkeys(SYMBOLS, 100.0)
    for index in range(count):
        for symbol_index, symbol in enumerate(SYMBOLS):
            change = 0.002 * (index % 5 - 2)
            if mode == "negative" and symbol_index == 1:
                change = -change
            if mode == "constant":
                change = 0
            closes[symbol] *= math.exp(change)
            result.append(
                Candle(
                    symbol=symbol,
                    window_start=START + STEP * index,
                    window_end=START + STEP * (index + 1),
                    window_seconds=60,
                    quality="observed",
                    close=Decimal(str(closes[symbol])),
                    completeness_note="Synthetic fixture only",
                )
            )
    return result


def replay(candles, config=None):
    config = config or policy()
    history = []
    for index in range(1, 1 + max(int((c.window_end - START) / STEP) for c in candles)):
        history.append(evaluate(candles, history, START + STEP * index, "source", 60, config))
    return history


def test_positive_and_negative_correlations():
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1)
    assert pearson([1, 2, 3], [6, 4, 2]) == pytest.approx(-1)
    for mode, expected in (("positive", 1), ("negative", -1)):
        result = replay(make_candles(mode=mode))[-1]
        assert result.pairs[0].coefficient == pytest.approx(expected)
        assert result.pairs[0].sample_count == 8
        assert result.pairs[0].coverage == 1


@pytest.mark.parametrize("xs,ys", [([1, 1, 1], [1, 2, 3]), ([0, 0], [0, 0]), ([], []), ([1], [2])])
def test_undefined_correlation(xs, ys):
    assert pearson(xs, ys) is None


def test_zero_variance_and_true_zero_returns():
    result = replay(make_candles(mode="constant"))[-1]
    assert all(p.status == "zero_variance" and p.coefficient is None for p in result.pairs)
    assert all(a.current_return == 0 and a.eligible_returns == 8 for a in result.assets)
    assert result.regime.label == "insufficient_data"


def test_insufficient_history_has_no_numeric_discovery():
    result = replay(make_candles(3))[-1]
    assert all(p.coefficient is None for p in result.pairs)
    assert not any(b.is_event for b in result.breakdowns)
    assert result.regime.label == "insufficient_data"


@pytest.mark.parametrize("quality", ["missing", "partial_start", "data_gap"])
def test_ineligible_windows_break_adjacent_returns(quality):
    candles = make_candles(12)
    candles = [
        c.model_copy(update={"quality": quality})
        if c.symbol == "ETHUSDT" and c.window_end == START + STEP * 8
        else c
        for c in candles
    ]
    returns, _ = aligned_returns(candles, 60, START + STEP * 7, START + STEP * 10)
    assert returns["ETHUSDT"][START + STEP * 8] is None
    assert returns["ETHUSDT"][START + STEP * 9] is None
    assert returns["BTCUSDT"][START + STEP * 8] is not None


def test_missing_candles_different_starts_and_pairwise_counts():
    candles = [
        c
        for c in make_candles(12)
        if not (c.symbol == "SOLUSDT" and c.window_end < START + STEP * 8)
    ]
    result = replay(candles)[-1]
    assert result.pairs[0].sample_count == 8
    assert result.pairs[1].sample_count == 4
    assert result.assets[2].eligible_returns == 4


def test_duplicate_and_utc_boundary_alignment():
    candles = make_candles(4)
    offset = timezone(timedelta(hours=5, minutes=30))
    returns, _ = aligned_returns(
        [*reversed(candles), candles[0]], 60, (START + STEP).astimezone(offset), START + STEP * 4
    )
    assert returns["BTCUSDT"][START + STEP] is None
    assert returns["BTCUSDT"][START + STEP * 2] is not None
    bad = candles[0].model_copy(update={"close": Decimal(999)})
    with pytest.raises(ValueError, match="conflicting"):
        aligned_returns([*candles, bad], 60, START + STEP, START + STEP * 4)
    with pytest.raises(ValueError, match="grid"):
        aligned_returns(candles, 60, START + timedelta(seconds=1), START + STEP * 4)


def test_no_future_leakage_and_stable_utc_id():
    candles = make_candles(30)
    time = START + STEP * 12
    expected = evaluate(
        [c for c in candles if c.window_end <= time], [], time, "source", 60, policy()
    )
    actual = evaluate(candles, replay(candles), time, "source", 60, policy())
    # Prior history changes baselines, so compare no-history evaluation for the leakage assertion.
    assert evaluate(candles, [], time, "source", 60, policy()) == expected
    assert actual.pairs[0].coefficient == expected.pairs[0].coefficient
    assert (
        evaluate(
            candles, [], time.astimezone(timezone(timedelta(hours=5))), "source", 60, policy()
        ).id
        == expected.id
    )


def test_robust_baseline_warmup_and_signed_breakdown():
    candles = make_candles(35)
    # Reverse ETH's movement after a strongly positive established baseline.
    for i, c in enumerate(candles):
        minute = int((c.window_end - START) / STEP)
        if c.symbol == "ETHUSDT" and minute >= 20:
            candles[i] = c.model_copy(update={"close": Decimal(10000) / c.close})
    results = replay(candles)
    assert all(not b.is_event for r in results[:7] for b in r.breakdowns)
    signals = [b for r in results for b in r.breakdowns if b.is_event]
    assert signals and any(b.direction == "weakening" for b in signals)
    assert all(b.effective_scale >= 0.05 for b in signals)
    assert all(b.baseline_count >= 3 for b in signals)
    assert any(r.regime.label in ("correlation_breakdown", "mixed_or_unstable") for r in results)


def test_baseline_resets_after_gaps_and_ignores_other_profiles():
    candles = make_candles()
    history = replay(candles)
    time = history[-1].window_end
    assert (
        evaluate(
            candles,
            [r.model_copy(update={"profile_id": "other"}) for r in history],
            time,
            "source",
            60,
            policy(),
        )
        .breakdowns[0]
        .baseline_count
        == 0
    )
    history[-2] = history[-2].model_copy(
        update={
            "pairs": [
                p.model_copy(update={"status": "current_ineligible", "coefficient": None})
                for p in history[-2].pairs
            ]
        }
    )
    assert (
        evaluate(candles, history, time, "source", 60, policy()).breakdowns[0].baseline_count == 0
    )


def test_lag_direction_no_gap_bridging_and_completed_targets():
    config = policy()
    times = [START + STEP * n for n in range(1, 15)]
    xs = [0.2, -0.1, 0.5, 0.3, -0.8, 0.7, -0.3, 0.9, 0.1, -0.4, 0.6, 0.2, -0.7, 0.8]
    returns = {
        "BTCUSDT": dict(zip(times, xs, strict=True)),
        "ETHUSDT": {t + STEP: x for t, x in zip(times, xs, strict=True)},
    }
    result = pair_stat("BTCUSDT", "ETHUSDT", returns, times[-8:], STEP, config, lag=1)
    assert result.coefficient == pytest.approx(1)
    returns["BTCUSDT"][times[-4]] = None
    gapped = pair_stat("BTCUSDT", "ETHUSDT", returns, times[-8:], STEP, config, lag=2)
    assert gapped.sample_count == 5  # the three lag chains touching the missing grid are excluded
    assert max(times[-8:]) <= times[-1]


def test_optional_oos_is_chronological_and_lag_is_frozen():
    config = CrossAssetConfig(
        lookback=20,
        min_pairs=5,
        min_coverage=0.5,
        baseline_windows=5,
        min_baseline=3,
        max_lag=2,
        oos_enabled=True,
        oos_min_pairs=4,
    )
    result = replay(make_candles(35), config)[-1]
    oos = result.lead_lag[0].out_of_sample
    assert oos.status == "ready" and oos.selected_lag in (1, 2)
    assert oos.split_time == result.window_end - STEP * 5
    assert oos.train_count <= 14 and oos.test_count <= 6
    assert "not forecast accuracy" in oos.explanation


def test_regime_normal_sync_elevated_and_mixed_rules():
    current = replay(make_candles())[-1]
    assert current.regime.label == "high_synchronization"
    normal_pairs = [p.model_copy(update={"coefficient": 0.3}) for p in current.pairs]
    assert (
        classify(
            current.window_end, current.assets, normal_pairs, current.breakdowns, policy()
        ).label
        == "normal_observed_conditions"
    )
    elevated = [a.model_copy(update={"elevated_volatility": True}) for a in current.assets]
    assert (
        classify(current.window_end, elevated, normal_pairs, current.breakdowns, policy()).label
        == "elevated_volatility"
    )
    assert (
        classify(current.window_end, elevated, current.pairs, current.breakdowns, policy()).label
        == "mixed_or_unstable"
    )


def test_profile_identity_includes_source_policy_and_statistical_settings():
    config = policy()
    assert config.profile_id("a", 60) != config.profile_id("b", 60)
    assert config.profile_id("a", 60) != config.profile_id("a", 30)
    assert config.profile_id("a", 60) != config.model_copy(update={"min_coverage": 0.9}).profile_id(
        "a", 60
    )
    with pytest.raises(ValidationError):
        CrossAssetConfig(min_pairs=100, lookback=10)


def test_oos_selection_cannot_use_test_targets():
    config = CrossAssetConfig(
        lookback=20,
        min_pairs=5,
        min_coverage=0.5,
        baseline_windows=5,
        min_baseline=3,
        max_lag=2,
        oos_enabled=True,
        oos_min_pairs=4,
    )
    times = [START + STEP * n for n in range(25)]
    xs = [math.sin(n * 1.7) / 100 for n in range(25)]
    returns = {
        "BTCUSDT": dict(zip(times, xs, strict=True)),
        "ETHUSDT": {t + STEP: v for t, v in zip(times, xs, strict=True)},
    }
    current_times = times[-20:]
    expected = lead_lag("BTCUSDT", "ETHUSDT", returns, current_times, STEP, config)
    split = current_times[14]
    for time in current_times:
        if time >= split:
            returns["ETHUSDT"][time] *= -1
    actual = lead_lag("BTCUSDT", "ETHUSDT", returns, current_times, STEP, config)
    assert actual.out_of_sample.selected_lag == expected.out_of_sample.selected_lag == 1
    assert actual.out_of_sample.train_coefficient == expected.out_of_sample.train_coefficient
    assert actual.out_of_sample.test_coefficient == pytest.approx(
        -expected.out_of_sample.test_coefficient
    )


def test_latest_ineligible_return_suppresses_old_numeric_correlation():
    candles = make_candles(30)
    candles[-2] = candles[-2].model_copy(update={"quality": "data_gap"})
    result = replay(candles)[-1]
    assert result.pairs[0].status == "current_ineligible"
    assert result.pairs[0].coefficient is None
