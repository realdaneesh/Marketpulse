"""Canonical validated trade representation; monetary values never use floats."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, computed_field, field_validator

PositiveDecimal = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]


class Trade(BaseModel):
    """An immutable exchange trade with UTC time and inferred taker direction."""

    model_config = ConfigDict(frozen=True)

    exchange: Literal["binance"] = "binance"
    symbol: str = Field(pattern=r"^[A-Z0-9]{2,30}$")
    trade_id: int = Field(ge=0, le=2**63 - 1, strict=True)
    price: PositiveDecimal
    quantity: PositiveDecimal
    timestamp: AwareDatetime
    buyer_maker: bool = Field(strict=True)

    @field_validator("timestamp")
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @computed_field
    @property
    def aggressor_side(self) -> Literal["buy", "sell"]:
        """A resting buyer implies the incoming aggressor was the seller."""
        return "sell" if self.buyer_maker else "buy"
