"""Translate raw or combined Binance trade messages into canonical trades."""

import json
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from marketpulse.models import PositiveDecimal, Trade

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class MalformedMessage(ValueError):
    """A payload cannot be safely interpreted as a Binance trade."""


class BinanceTrade(BaseModel):
    """Required exchange fields; unrelated metadata may evolve independently."""

    e: Literal["trade"]
    s: str = Field(pattern=r"^[A-Z0-9]{2,30}$")
    t: int = Field(ge=0, le=2**63 - 1, strict=True)
    p: PositiveDecimal
    q: PositiveDecimal
    T: int = Field(ge=0, le=253402300799999, strict=True)
    m: bool = Field(strict=True)


def parse_trade(message: str | bytes) -> Trade:
    """Validate one message, preserving decimal precision and millisecond UTC time."""
    try:
        payload = json.loads(message)
        if not isinstance(payload, dict):
            raise ValueError("expected a JSON object")
        envelope = payload if "stream" in payload else None
        if envelope is not None:
            payload = envelope.get("data")
        raw = BinanceTrade.model_validate(payload)
        if envelope is not None and envelope["stream"] != f"{raw.s.lower()}@trade":
            raise ValueError("stream name does not match trade symbol")
        return Trade(
            symbol=raw.s,
            trade_id=raw.t,
            price=raw.p,
            quantity=raw.q,
            timestamp=EPOCH + timedelta(milliseconds=raw.T),
            buyer_maker=raw.m,
        )
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise MalformedMessage("invalid Binance trade payload") from exc
