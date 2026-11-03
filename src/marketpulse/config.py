"""Validated environment configuration shared by the API and collector."""

import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from marketpulse.analytics.config import AnalyticsConfig
from marketpulse.cross_asset.config import CrossAssetConfig


class Settings(BaseSettings):
    """Load MARKETPULSE_* variables, optionally from a local .env file."""

    model_config = SettingsConfigDict(
        env_prefix="MARKETPULSE_", env_file=".env", extra="ignore", env_nested_delimiter="__"
    )

    database_path: Path = Path("data/marketpulse.sqlite3")
    symbols: Annotated[tuple[str, ...], NoDecode] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    websocket_url: str = "wss://data-stream.binance.vision"
    batch_size: int = Field(default=250, ge=1, le=10000)
    flush_interval: float = Field(default=1.0, gt=0, le=60)
    queue_size: int = Field(default=10000, ge=1, le=1000000)
    reconnect_base: float = Field(default=1.0, gt=0, le=300)
    reconnect_max: float = Field(default=60.0, gt=0, le=3600)
    stable_connection_seconds: float = Field(default=60.0, gt=0)
    open_timeout: float = Field(default=15.0, gt=0)
    receive_timeout: float = Field(default=60.0, gt=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    display_trades: bool = True
    analytics: AnalyticsConfig = Field(default_factory=AnalyticsConfig)
    cross_asset: CrossAssetConfig = Field(default_factory=CrossAssetConfig)
    cross_asset_batch_size: int = Field(default=128, ge=1, le=1000)
    cross_asset_poll_interval: float = Field(default=5.0, gt=0, le=3600)
    analytics_page_size: int = Field(default=2000, ge=1, le=50000)
    analytics_max_windows: int = Field(default=1000, ge=1, le=100000)
    analytics_poll_interval: float = Field(default=2.0, gt=0, le=3600)

    @field_validator("symbols", mode="before")
    @classmethod
    def parse_symbols(cls, value: object) -> tuple[str, ...]:
        """Accept comma-separated environment values and normalize symbols."""
        if isinstance(value, str):
            value = value.split(",")
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("symbols must be a nonempty sequence")
        symbols = tuple(dict.fromkeys(str(item).strip().upper() for item in value))
        if any(not re.fullmatch(r"[A-Z0-9]{2,30}", item) for item in symbols):
            raise ValueError("symbols must contain only ASCII letters and digits")
        return symbols

    @field_validator("websocket_url")
    @classmethod
    def public_endpoint(cls, value: str) -> str:
        """Restrict collection to Binance's unauthenticated market-data endpoint."""
        if value.rstrip("/") != "wss://data-stream.binance.vision":
            raise ValueError("use wss://data-stream.binance.vision")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_backoff(self) -> "Settings":
        if self.reconnect_max < self.reconnect_base:
            raise ValueError("reconnect_max must be at least reconnect_base")
        return self

    @property
    def stream_url(self) -> str:
        streams = "/".join(f"{symbol.lower()}@trade" for symbol in self.symbols)
        return f"{self.websocket_url}/stream?streams={streams}"
