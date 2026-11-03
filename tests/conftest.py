"""Synthetic exchange-shaped fixtures; never used by runtime collection."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from marketpulse.analytics.config import AnalyticsConfig
from marketpulse.config import Settings
from marketpulse.models import Trade


@pytest.fixture
def payload() -> dict:
    return {
        "e": "trade",
        "E": 1700000000999,
        "s": "BTCUSDT",
        "t": 123,
        "p": "35000.12345678",
        "q": "0.00001234",
        "T": 1700000000123,
        "m": True,
        "M": True,
    }


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        database_path=tmp_path / "trades.sqlite3",
        batch_size=3,
        flush_interval=0.02,
        queue_size=2,
        reconnect_base=0.001,
        reconnect_max=0.01,
        display_trades=False,
    )


@pytest.fixture
def analytics_settings(settings):
    return settings.model_copy(
        update={
            "analytics": AnalyticsConfig(
                min_history=3,
                history_size=6,
                allowed_lateness_seconds=0,
                min_imbalance_trades=2,
                min_imbalance_quote_volume=1,
            ),
            "analytics_page_size": 3,
        }
    )


@pytest.fixture
def make_trade():
    def make(seconds=0, trade_id=1, price="100", quantity="1", maker=False, symbol="BTCUSDT"):
        return Trade(
            symbol=symbol,
            trade_id=trade_id,
            price=Decimal(price),
            quantity=Decimal(quantity),
            timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(seconds=seconds),
            buyer_maker=maker,
        )

    return make


@pytest.fixture
def make_windows(make_trade):
    def make(count=9, shock_at=6, symbol="BTCUSDT"):
        trades = []
        for minute in range(count):
            prices = ("120", "80", "140", "120") if minute == shock_at else ("100",) * 4
            for index, price in enumerate(prices):
                trades.append(
                    make_trade(
                        seconds=minute * 60 + index * 10,
                        trade_id=minute * 4 + index + 1,
                        price=price,
                        quantity="1000" if minute == shock_at else "1",
                        maker=False if minute == shock_at else bool(index % 2),
                        symbol=symbol,
                    )
                )
        return trades

    return make
