import math
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from marketpulse.analytics.aggregation import CandleAccumulator, aggregate_trades, window_start

START = datetime(2024, 1, 1, tzinfo=UTC)


def test_ohlcv_vwap_imbalance_and_realized_volatility(make_trade):
    trades = [
        make_trade(0, 1, "100", "2"),
        make_trade(20, 2, "120", "1", maker=True),
        make_trade(40, 3, "90", "3"),
    ]
    candle = aggregate_trades(trades, "BTCUSDT", START)
    assert (candle.open, candle.high, candle.low, candle.close) == tuple(
        map(Decimal, (100, 120, 90, 90))
    )
    assert candle.base_volume == Decimal(6)
    assert candle.quote_volume == Decimal(590)
    assert float(candle.vwap) == pytest.approx(590 / 6)
    assert candle.aggressive_buy_volume == Decimal(5)
    assert candle.aggressive_sell_volume == Decimal(1)
    assert candle.signed_imbalance == pytest.approx(4 / 6)
    assert candle.realized_volatility == pytest.approx(
        math.sqrt(math.log(1.2) ** 2 + math.log(0.75) ** 2)
    )
    assert candle.trade_count == 3
    assert candle.log_return is None


def test_ordering_duplicate_timestamps_and_deduplication(make_trade):
    trades = [make_trade(10, 3, "110"), make_trade(10, 1, "100"), make_trade(10, 2, "90")]
    result = aggregate_trades([*trades, trades[0]], "BTCUSDT", START)
    assert result.open == Decimal(100)
    assert result.close == Decimal(110)
    assert result.trade_count == 3
    with pytest.raises(ValueError, match="conflicting"):
        aggregate_trades([trades[0], make_trade(10, 3, "500")], "BTCUSDT", START)


def test_empty_interval_unknown_volume_and_single_trade_volatility(make_trade):
    empty = aggregate_trades([], "BTCUSDT", START)
    assert empty.quality == "missing"
    assert empty.base_volume is None and empty.quote_volume is None
    assert empty.vwap is None and empty.signed_imbalance is None
    assert empty.missing_intervals == 1
    single = aggregate_trades([make_trade()], "BTCUSDT", START)
    assert single.realized_volatility is None


def test_returns_require_adjacent_eligible_candles(make_trade):
    previous = aggregate_trades([make_trade()], "BTCUSDT", START)
    next_candle = aggregate_trades(
        [make_trade(60, 2, "110")], "BTCUSDT", START + timedelta(minutes=1), previous=previous
    )
    assert next_candle.log_return == pytest.approx(math.log(1.1))
    later = aggregate_trades(
        [make_trade(120, 3)], "BTCUSDT", START + timedelta(minutes=2), previous=previous
    )
    assert later.log_return is None
    partial = previous.model_copy(update={"quality": "partial_start"})
    assert (
        aggregate_trades(
            [make_trade(60, 2)], "BTCUSDT", START + timedelta(minutes=1), previous=partial
        ).log_return
        is None
    )


def test_decimal_precision_and_half_open_boundaries(make_trade):
    result = aggregate_trades(
        [make_trade(price="1.123456789123456789", quantity="2")], "BTCUSDT", START
    )
    assert result.quote_volume == Decimal("2.246913578246913578")
    with pytest.raises(ValueError, match="belong"):
        aggregate_trades([make_trade(60)], "BTCUSDT", START)
    with pytest.raises(ValueError, match="belong"):
        aggregate_trades([make_trade(symbol="SOLUSDT")], "BTCUSDT", START)
    assert window_start(START + timedelta(seconds=59, microseconds=999999), 60) == START
    assert window_start(START.astimezone(timezone(timedelta(hours=5, minutes=30))), 60) == START
    with pytest.raises(ValueError):
        window_start(datetime(2024, 1, 1), 60)


def test_streaming_accumulator_rejects_unsorted_input(make_trade):
    accumulator = CandleAccumulator("BTCUSDT", START, 60)
    accumulator.add(make_trade(20, 2))
    with pytest.raises(ValueError, match="ordered"):
        accumulator.add(make_trade(10, 1))
