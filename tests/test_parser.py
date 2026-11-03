import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from marketpulse.ingestion.parser import MalformedMessage, parse_trade


@pytest.mark.parametrize("combined", [False, True])
@pytest.mark.parametrize("maker,side", [(True, "sell"), (False, "buy")])
def test_parse_precision_utc_and_aggressor(payload, combined, maker, side):
    payload["m"] = maker
    message = {"stream": "btcusdt@trade", "data": payload} if combined else payload
    trade = parse_trade(json.dumps(message))
    assert trade.exchange == "binance"
    assert trade.symbol == "BTCUSDT"
    assert trade.trade_id == 123
    assert trade.price == Decimal("35000.12345678")
    assert trade.quantity == Decimal("0.00001234")
    assert trade.timestamp == datetime(2023, 11, 14, 22, 13, 20, 123000, tzinfo=UTC)
    assert trade.aggressor_side == side
    assert trade.buyer_maker is maker
    assert trade.model_dump(mode="json")["price"] == "35000.12345678"


@pytest.mark.parametrize(
    "message",
    [
        "not JSON",
        "[]",
        "null",
        "42",
        "{}",
        '{"data": null, "stream": "btcusdt@trade"}',
        '{"result": null, "id": 1}',
        b"\xff",
        '{"code":2,"msg":"error"}',
    ],
)
def test_malformed_shapes(message):
    with pytest.raises(MalformedMessage):
        parse_trade(message)


@pytest.mark.parametrize(
    "field,value",
    [
        ("p", "NaN"),
        ("p", "Infinity"),
        ("p", "-1"),
        ("p", "0"),
        ("q", "0"),
        ("q", "bad"),
        ("m", "false"),
        ("m", 1),
        ("t", -1),
        ("t", True),
        ("t", 2**63),
        ("T", -1),
        ("T", 10**30),
        ("T", "1700000000123"),
        ("s", "btc/usdt"),
        ("e", "aggTrade"),
    ],
)
def test_invalid_fields(payload, field, value):
    payload[field] = value
    with pytest.raises(MalformedMessage):
        parse_trade(json.dumps(payload))


def test_missing_field_and_envelope_mismatch(payload):
    with pytest.raises(MalformedMessage):
        parse_trade(json.dumps({"stream": "ethusdt@trade", "data": payload}))
    del payload["p"]
    with pytest.raises(MalformedMessage):
        parse_trade(json.dumps(payload))


def test_deeply_nested_malformed_json():
    with pytest.raises(MalformedMessage):
        parse_trade("[" * 2000 + "]" * 2000)
