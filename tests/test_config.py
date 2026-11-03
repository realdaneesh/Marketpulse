import pytest
from pydantic import ValidationError

from marketpulse.config import Settings


def test_environment_configuration(monkeypatch):
    monkeypatch.setenv("MARKETPULSE_SYMBOLS", "btcusdt, ETHUSDT,btcusdt")
    monkeypatch.setenv("MARKETPULSE_BATCH_SIZE", "25")
    settings = Settings(_env_file=None)
    assert settings.symbols == ("BTCUSDT", "ETHUSDT")
    assert settings.batch_size == 25


@pytest.mark.parametrize(
    "values",
    [
        {"symbols": ""},
        {"symbols": "BTC/USDT"},
        {"batch_size": 0},
        {"reconnect_base": 10, "reconnect_max": 1},
        {"websocket_url": "wss://example.com"},
    ],
)
def test_invalid_configuration(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
