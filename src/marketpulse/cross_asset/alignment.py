"""Exact UTC alignment and adjacent eligible close returns; no imputation."""

import math
from datetime import UTC, datetime, timedelta

from marketpulse.analytics.aggregation import log_ratio, window_start
from marketpulse.analytics.models import Candle
from marketpulse.cross_asset.config import SYMBOLS


def index_candles(candles: list[Candle], seconds: int, through: datetime) -> dict:
    index = {}
    for candle in candles:
        if candle.symbol not in SYMBOLS or candle.window_end > through:
            continue
        start = candle.window_start.astimezone(UTC)
        end = candle.window_end.astimezone(UTC)
        if (
            candle.window_seconds != seconds
            or window_start(start, seconds) != start
            or window_start(end, seconds) != end
            or end <= start
        ):
            raise ValueError("source candle is not on the configured UTC grid")
        if candle.quality != "missing" and end - start != timedelta(seconds=seconds):
            raise ValueError("non-missing candle must occupy exactly one grid interval")
        key = (candle.symbol, end)
        if key in index and index[key] != candle:
            raise ValueError("conflicting finalized candles")
        index[key] = candle
    return index


def eligible(candle: Candle | None, seconds: int) -> bool:
    return (
        candle is not None
        and candle.quality == "observed"
        and candle.window_end - candle.window_start == timedelta(seconds=seconds)
        and candle.close is not None
        and candle.close.is_finite()
        and candle.close > 0
    )


def aligned_returns(
    candles: list[Candle], seconds: int, start: datetime, through: datetime
) -> tuple[dict, dict]:
    """Map window END times to finite returns or None, retaining real zeroes.

    Caller supplies a preceding candle for return calculation. Recompute from closes
    rather than trusting a persisted return divorced from its eligibility context.
    """
    if start.tzinfo is None or through.tzinfo is None:
        raise ValueError("timezone-aware grid required")
    if window_start(start, seconds) != start or window_start(through, seconds) != through:
        raise ValueError("aligned grid boundaries required")
    index = index_candles(candles, seconds, through)
    returns = {symbol: {} for symbol in SYMBOLS}
    coverage = {symbol: {} for symbol in SYMBOLS}
    time = start
    step = timedelta(seconds=seconds)
    while time <= through:
        for symbol in SYMBOLS:
            current, previous = index.get((symbol, time)), index.get((symbol, time - step))
            coverage[symbol][time] = eligible(current, seconds)
            value = None
            if eligible(current, seconds) and eligible(previous, seconds):
                value = log_ratio(current.close, previous.close)
                if not math.isfinite(value):
                    value = None
            returns[symbol][time] = value
        time += step
    return returns, coverage
