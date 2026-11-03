"""Causal descriptive statistics, robust relationship deviations and explicit rules."""

import hashlib
import math
from datetime import UTC, datetime, timedelta
from statistics import fmean, median

from marketpulse.analytics.models import Candle
from marketpulse.cross_asset.alignment import aligned_returns
from marketpulse.cross_asset.config import PAIRS, SYMBOLS, CrossAssetConfig
from marketpulse.cross_asset.models import (
    AssetStatistic,
    Breakdown,
    CrossSnapshot,
    LagStatistic,
    LeadLag,
    OutOfSample,
    PairStatistic,
    Regime,
)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys) or not all(map(math.isfinite, [*xs, *ys])):
        return None
    # Normalize first to avoid overflow/underflow of squared centered deviations.
    sx, sy = max(map(abs, xs)), max(map(abs, ys))
    if not sx or not sy:
        return None
    ax, ay = [v / sx for v in xs], [v / sy for v in ys]
    mx, my = fmean(ax), fmean(ay)
    dx, dy = [x - mx for x in ax], [y - my for y in ay]
    xx, yy = math.fsum(x * x for x in dx), math.fsum(y * y for y in dy)
    if not xx or not yy:
        return None
    return max(
        -1.0, min(1.0, math.fsum(x * y for x, y in zip(dx, dy, strict=True)) / math.sqrt(xx * yy))
    )


def volatility(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = fmean(values)
    return math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (len(values) - 1))


def pair_stat(
    a: str,
    b: str,
    returns: dict,
    times: list[datetime],
    step: timedelta,
    config: CrossAssetConfig,
    lag: int = 0,
    minimum: int | None = None,
    require_current: bool = True,
) -> PairStatistic:
    matched = []
    for time in times:
        # Require the intervening grids too: no lag association spans a data gap.
        chain = [time - step * k for k in range(lag + 1)]
        if all(returns[symbol].get(t) is not None for symbol in (a, b) for t in chain):
            matched.append((returns[a][time - step * lag], returns[b][time]))
    count, expected = len(matched), len(times)
    coverage = count / expected if expected else 0
    status = "ready"
    if count < (minimum if minimum is not None else config.min_pairs):
        status = "insufficient_history"
    elif coverage < config.min_coverage:
        status = "insufficient_coverage"
    elif require_current and any(
        returns[s].get(times[-1] - step * k) is None for s in (a, b) for k in range(lag + 1)
    ):
        status = "current_ineligible"
    coefficient = None
    if status == "ready":
        coefficient = pearson([x for x, _ in matched], [y for _, y in matched])
        if coefficient is None:
            status = "zero_variance"
    return PairStatistic(
        asset_a=a,
        asset_b=b,
        status=status,
        coefficient=coefficient,
        sample_count=count,
        expected_count=expected,
        coverage=coverage,
        explanation=f"{count}/{expected} synchronized eligible returns; {status}. "
        "Missing and uncertain windows are excluded; zero returns are retained.",
    )


def preceding(
    history: list[CrossSnapshot], time: datetime, step: timedelta, length: int
) -> list[CrossSnapshot]:
    by_time = {item.window_end: item for item in history if item.window_end < time}
    result = []
    cursor = time - step
    while len(result) < length and cursor in by_time:
        result.append(by_time[cursor])
        cursor -= step
    return result


def breakdown(
    pair: PairStatistic, prior: list[CrossSnapshot], config: CrossAssetConfig
) -> Breakdown:
    values = []
    for snapshot in prior:
        old = next(
            p for p in snapshot.pairs if (p.asset_a, p.asset_b) == (pair.asset_a, pair.asset_b)
        )
        if old.status != "ready" or old.coefficient is None:
            break
        values.append(old.coefficient)
    common = {"asset_a": pair.asset_a, "asset_b": pair.asset_b, "baseline_count": len(values)}
    if pair.coefficient is None or pair.status != "ready":
        return Breakdown(
            **common,
            status="unavailable",
            direction="unavailable",
            explanation="Current relationship is ineligible; no deviation or event.",
        )
    if len(values) < config.min_baseline:
        return Breakdown(
            **common,
            status="insufficient_history",
            direction="unavailable",
            explanation=f"Baseline warm-up: {len(values)}/{config.min_baseline} "
            "preceding eligible rolling windows. No event.",
        )
    center = median(values)
    mad = median([abs(v - center) for v in values])
    scale = max(1.4826 * mad, config.correlation_scale_floor)
    delta = pair.coefficient - center
    score = min(100.0, abs(delta) / scale)
    event = score >= config.deviation_threshold and abs(delta) >= config.min_correlation_change
    direction = "strengthening" if delta > 0 else "weakening" if delta < 0 else "unchanged"
    return Breakdown(
        **common,
        status="ready",
        baseline_median=center,
        baseline_mad=mad,
        effective_scale=scale,
        deviation_score=score,
        change_from_baseline=delta,
        direction=direction,
        is_event=event,
        explanation=f"Signed correlation {direction}: delta={delta:.6g}, "
        f"preceding median={center:.6g}, "
        f"MAD={mad:.6g}, scale=max(1.4826*MAD,{config.correlation_scale_floor})={scale:.6g}; "
        f"|delta|/scale={score:.6g} (capped at 100). Gates: score >= {config.deviation_threshold}, "
        f"|delta| >= {config.min_correlation_change}. Overlapping windows are dependent; "
        "this heuristic is not a probability or significance test.",
    )


def lead_lag(
    a: str, b: str, returns: dict, times: list[datetime], step: timedelta, config: CrossAssetConfig
) -> LeadLag:
    lags = [
        LagStatistic(**pair_stat(a, b, returns, times, step, config, lag).model_dump(), lag=lag)
        for lag in range(1, config.max_lag + 1)
    ]
    ready = [item for item in lags if item.coefficient is not None]
    selected = (
        max(ready, key=lambda item: (abs(item.coefficient), -item.lag)).lag if ready else None
    )
    oos = OutOfSample(
        status="disabled",
        explanation="Chronological association stability evaluation disabled; "
        "no directional performance claim.",
    )
    if config.oos_enabled:
        split = int(len(times) * config.train_fraction)
        train_times, test_times = times[:split], times[split:]
        train = [
            LagStatistic(
                **pair_stat(
                    a, b, returns, train_times, step, config, k, config.oos_min_pairs, False
                ).model_dump(),
                lag=k,
            )
            for k in range(1, config.max_lag + 1)
        ]
        candidates = [item for item in train if item.coefficient is not None]
        oos = OutOfSample(
            status="insufficient_history",
            split_time=test_times[0],
            explanation="Fixed chronological grid split lacks eligible training/test support; "
            "no performance claim.",
        )
        if candidates:
            best = max(candidates, key=lambda item: (abs(item.coefficient), -item.lag))
            test = pair_stat(
                a, b, returns, test_times, step, config, best.lag, config.oos_min_pairs
            )
            oos = OutOfSample(
                status="ready" if test.coefficient is not None else "insufficient_history",
                split_time=test_times[0],
                selected_lag=best.lag,
                train_coefficient=best.coefficient,
                test_coefficient=test.coefficient,
                train_count=best.sample_count,
                test_count=test.sample_count,
                train_coverage=best.coverage,
                test_coverage=test.coverage,
                explanation="Lag selected only on first chronological segment "
                "by absolute correlation; frozen lag evaluated on later targets. "
                "This measures held-out association stability, "
                "not forecast accuracy, trading performance, or causation. "
                "Repeated rolling splits are dependent.",
            )
    return LeadLag(
        leader=a,
        follower=b,
        lags=lags,
        exploratory_selected_lag=selected,
        out_of_sample=oos,
        explanation=f"{a} leads {b} by k intervals means r_{a}(t) versus r_{b}(t+k). "
        "Every target is finalized by publication time. "
        "Lag selection is exploratory with multiple-testing risk; "
        "association is neither causation nor demonstrated predictive performance.",
    )


def classify(
    time: datetime,
    assets: list[AssetStatistic],
    pairs: list[PairStatistic],
    signals: list[Breakdown],
    config: CrossAssetConfig,
) -> Regime:
    ready = [p for p in pairs if p.status == "ready"]
    elevated = [a.symbol for a in assets if a.elevated_volatility]
    broken = [f"{b.asset_a}–{b.asset_b}" for b in signals if b.is_event]
    mean = fmean(p.coefficient for p in ready) if ready else None
    established = (
        len(ready) == 3
        and all(b.status == "ready" for b in signals)
        and all(a.baseline_count >= config.min_baseline for a in assets)
    )
    synchronized = len(ready) == 3 and all(
        p.coefficient >= config.synchronization_threshold for p in ready
    )
    if not established:
        label = "insufficient_data"
    elif (broken and (elevated or synchronized)) or (elevated and synchronized):
        label = "mixed_or_unstable"
    elif broken:
        label = "correlation_breakdown"
    elif elevated:
        label = "elevated_volatility"
    elif synchronized:
        label = "high_synchronization"
    else:
        label = "normal_observed_conditions"
    return Regime(
        label=label,
        evidence_time=time,
        data_quality="eligible"
        if established
        else "incomplete"
        if any(a.current_return is None for a in assets)
        else "insufficient",
        ready_pairs=len(ready),
        elevated_assets=elevated,
        breakdown_pairs=broken,
        mean_correlation=mean,
        thresholds={
            "synchronization": config.synchronization_threshold,
            "volatility_multiplier": config.volatility_multiplier,
            "volatility_floor": config.volatility_floor,
            "deviation_threshold": config.deviation_threshold,
            "minimum_change": config.min_correlation_change,
            "minimum_coverage": config.min_coverage,
            "minimum_baseline": config.min_baseline,
        },
        explanation=f"Rule label: {label}; {len(ready)}/3 ready pairs, "
        f"{len(elevated)} elevated-volatility assets, {len(broken)} changed relationships. "
        "All pair and volatility baselines are required for a supported regime. "
        "Descriptive observed conditions; no trading signal or crash forecast.",
    )


def evaluate(
    candles: list[Candle],
    history: list[CrossSnapshot],
    time: datetime,
    source_profile: str,
    seconds: int,
    config: CrossAssetConfig,
) -> CrossSnapshot:
    if time.tzinfo is None:
        raise ValueError("timezone-aware evaluation time required")
    time = time.astimezone(UTC)
    profile = config.profile_id(source_profile, seconds)
    history = [h for h in history if h.profile_id == profile and h.window_seconds == seconds]
    step = timedelta(seconds=seconds)
    times = [time - step * n for n in reversed(range(config.lookback))]
    returns, coverage = aligned_returns(candles, seconds, times[0] - step * config.max_lag, time)
    prior = preceding(history, time, step, config.baseline_windows)
    assets = []
    for symbol in SYMBOLS:
        values = [returns[symbol][t] for t in times if returns[symbol][t] is not None]
        support = (
            len(values) >= config.min_pairs and len(values) / len(times) >= config.min_coverage
        )
        vol = volatility(values) if support and returns[symbol][time] is not None else None
        baseline = []
        for item in prior:
            asset = next(a for a in item.assets if a.symbol == symbol)
            if asset.return_volatility is None:
                break
            baseline.append(asset.return_volatility)
        center = median(baseline) if len(baseline) >= config.min_baseline else None
        assets.append(
            AssetStatistic(
                symbol=symbol,
                eligible_returns=len(values),
                eligible_candles=sum(coverage[symbol][t] for t in times),
                expected_count=len(times),
                coverage=len(values) / len(times),
                return_volatility=vol,
                current_return=returns[symbol][time],
                volatility_baseline=center,
                baseline_count=len(baseline),
                elevated_volatility=vol is not None
                and center is not None
                and vol > max(config.volatility_multiplier * center, config.volatility_floor),
            )
        )
    pairs = [pair_stat(a, b, returns, times, step, config) for a, b in PAIRS]
    for pair in pairs:
        if prior:
            old = next(
                p for p in prior[0].pairs if (p.asset_a, p.asset_b) == (pair.asset_a, pair.asset_b)
            )
            if old.coefficient is not None and pair.coefficient is not None:
                pair_index = pairs.index(pair)
                pairs[pair_index] = pair.model_copy(
                    update={"change": pair.coefficient - old.coefficient}
                )
    signals = [breakdown(pair, prior, config) for pair in pairs]
    identifier = hashlib.sha256(f"{profile}|{time.isoformat()}".encode()).hexdigest()
    return CrossSnapshot(
        id=identifier,
        profile_id=profile,
        source_profile_id=source_profile,
        window_end=time,
        window_seconds=seconds,
        lookback=config.lookback,
        status="ready" if all(p.status == "ready" for p in pairs) else "insufficient_history",
        assets=assets,
        pairs=pairs,
        breakdowns=signals,
        lead_lag=[
            lead_lag(a, b, returns, times, step, config) for a in SYMBOLS for b in SYMBOLS if a != b
        ],
        regime=classify(time, assets, pairs, signals, config),
        explanation="Only finalized observed candles with adjacent observed closes enter returns. "
        "The common publication boundary is the minimum finalized boundary "
        "across all three sources.",
    )
