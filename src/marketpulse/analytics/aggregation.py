"""UTC candle aggregation with deterministic timestamp/trade-ID ordering."""

import math
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext

from marketpulse.analytics.models import Candle, Quality
from marketpulse.models import Trade

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def window_start(timestamp: datetime, seconds: int) -> datetime:
    """Floor aware event time to UTC epoch-aligned half-open windows."""
    if timestamp.tzinfo is None or seconds <= 0:
        raise ValueError("aware timestamp and positive window length required")
    delta = timestamp.astimezone(UTC) - EPOCH
    whole_seconds = delta.days * 86400 + delta.seconds
    return EPOCH + timedelta(seconds=(whole_seconds // seconds) * seconds)


def log_ratio(current: Decimal, previous: Decimal) -> float:
    """Use Decimal logarithms before converting, avoiding float ratio overflow."""
    with localcontext() as ctx:
        ctx.prec = 50
        return float((current / previous).ln())


class CandleAccumulator:
    """Constant-memory accumulator over ordered, unique trades from SQLite."""

    def __init__(self, symbol: str, start: datetime, seconds: int) -> None:
        self.symbol, self.start, self.seconds = symbol, start, seconds
        self.end = start + timedelta(seconds=seconds)
        self.open: Decimal | None = None
        self.high: Decimal | None = None
        self.low: Decimal | None = None
        self.close: Decimal | None = None
        self.base = Decimal(0)
        self.quote = Decimal(0)
        self.buy = Decimal(0)
        self.sell = Decimal(0)
        self.count = 0
        self.squared_returns = 0.0
        self.first_id: int | None = None
        self.last_id: int | None = None
        self.previous_key: tuple[datetime, int] | None = None

    def add(self, trade: Trade) -> None:
        """Reject cross-symbol/out-of-window records and incorrectly ordered input."""
        if trade.symbol != self.symbol or not self.start <= trade.timestamp < self.end:
            raise ValueError("trade does not belong to this symbol/window")
        key = (trade.timestamp, trade.trade_id)
        if self.previous_key is not None and key <= self.previous_key:
            raise ValueError("accumulator requires unique timestamp/trade-ID ordered records")
        if self.close is not None:
            self.squared_returns += log_ratio(trade.price, self.close) ** 2
        with localcontext() as ctx:
            ctx.prec = 50
            self.base += trade.quantity
            self.quote += trade.price * trade.quantity
            if trade.buyer_maker:
                self.sell += trade.quantity
            else:
                self.buy += trade.quantity
        self.open = trade.price if self.open is None else self.open
        self.high = trade.price if self.high is None else max(self.high, trade.price)
        self.low = trade.price if self.low is None else min(self.low, trade.price)
        self.close = trade.price
        self.first_id = (
            trade.trade_id if self.first_id is None else min(self.first_id, trade.trade_id)
        )
        self.last_id = trade.trade_id if self.last_id is None else max(self.last_id, trade.trade_id)
        self.count += 1
        self.previous_key = key

    def finish(self, previous: Candle | None = None, quality: Quality = "observed") -> Candle:
        if not self.count:
            return missing_candle(self.symbol, self.start, self.end, self.seconds)
        with localcontext() as ctx:
            ctx.prec = 50
            vwap = self.quote / self.base if self.base else None
            imbalance = float((self.buy - self.sell) / self.base) if self.base else None
        log_return = None
        if (
            previous is not None
            and previous.symbol == self.symbol
            and previous.window_seconds == self.seconds
            and previous.window_end == self.start
            and previous.quality == "observed"
            and quality == "observed"
            and previous.close is not None
            and self.close is not None
        ):
            log_return = log_ratio(self.close, previous.close)
        return Candle(
            symbol=self.symbol,
            window_start=self.start,
            window_end=self.end,
            window_seconds=self.seconds,
            quality=quality,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            base_volume=self.base,
            quote_volume=self.quote,
            trade_count=self.count,
            aggressive_buy_volume=self.buy,
            aggressive_sell_volume=self.sell,
            vwap=vwap,
            signed_imbalance=imbalance,
            log_return=log_return,
            realized_volatility=math.sqrt(self.squared_returns) if self.count >= 2 else None,
            first_trade_id=self.first_id,
            last_trade_id=self.last_id,
            completeness_note={
                "observed": "Final under watermark; no ID gap detected. Coverage not certified.",
                "partial_start": "First observed interval: collection start coverage is unknown.",
                "data_gap": "Missing interval or trade ID gap implies incomplete coverage.",
                "missing": "No collected trades; exchange activity is unknown.",
            }[quality],
        )


def missing_candle(symbol: str, start: datetime, end: datetime, seconds: int) -> Candle:
    """Represent a missing interval range without manufacturing zero market volume."""
    return Candle(
        symbol=symbol,
        window_start=start,
        window_end=end,
        window_seconds=seconds,
        quality="missing",
        missing_intervals=int((end - start).total_seconds()) // seconds,
        completeness_note="No collected trades in range; market activity is unknown, not zero.",
    )


def aggregate_trades(
    trades: Iterable[Trade],
    symbol: str,
    start: datetime,
    seconds: int = 60,
    previous: Candle | None = None,
) -> Candle:
    """Convenience aggregation for bounded inputs; sort and deduplicate by exchange key.

    The database worker instead streams ordered records into CandleAccumulator.
    Conflicting duplicates are rejected rather than choosing an arbitrary price.
    """
    unique: dict[tuple[str, str, int], Trade] = {}
    for trade in trades:
        key = (trade.exchange, trade.symbol, trade.trade_id)
        if key in unique and unique[key] != trade:
            raise ValueError("conflicting duplicate trade")
        unique[key] = trade
    accumulator = CandleAccumulator(symbol, start, seconds)
    for trade in sorted(unique.values(), key=lambda t: (t.timestamp, t.trade_id)):
        accumulator.add(trade)
    return accumulator.finish(previous)
