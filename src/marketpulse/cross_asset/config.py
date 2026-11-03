"""Versioned research policy, independent of Phase 2's immutable source policy."""

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
PAIRS = (("BTCUSDT", "ETHUSDT"), ("BTCUSDT", "SOLUSDT"), ("ETHUSDT", "SOLUSDT"))


class CrossAssetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    algorithm_version: Literal["v1"] = "v1"
    lookback: int = Field(default=60, ge=4, le=1000)
    min_pairs: int = Field(default=30, ge=3, le=1000)
    min_coverage: float = Field(default=0.8, gt=0, le=1)
    baseline_windows: int = Field(default=60, ge=3, le=1000)
    min_baseline: int = Field(default=20, ge=3, le=1000)
    correlation_scale_floor: float = Field(default=0.05, gt=0, le=1)
    deviation_threshold: float = Field(default=3.5, gt=0)
    min_correlation_change: float = Field(default=0.2, gt=0, le=2)
    max_lag: int = Field(default=3, ge=1, le=10)
    oos_enabled: bool = False
    train_fraction: float = Field(default=0.7, ge=0.5, le=0.8)
    oos_min_pairs: int = Field(default=10, ge=3, le=1000)
    synchronization_threshold: float = Field(default=0.8, gt=0, le=1)
    volatility_multiplier: float = Field(default=2.0, gt=1)
    volatility_floor: float = Field(default=0.000001, gt=0)

    @model_validator(mode="after")
    def consistent(self) -> "CrossAssetConfig":
        if self.min_pairs > self.lookback or self.min_baseline > self.baseline_windows:
            raise ValueError("minimum support cannot exceed its lookback")
        if self.max_lag >= self.lookback:
            raise ValueError("max_lag must be smaller than lookback")
        if (
            self.oos_enabled
            and min(
                int(self.lookback * self.train_fraction),
                self.lookback - int(self.lookback * self.train_fraction),
            )
            < self.oos_min_pairs
        ):
            raise ValueError("OOS training and test grid segments must support oos_min_pairs")
        return self

    def profile_id(self, source_profile: str, window_seconds: int) -> str:
        payload = {
            "policy": self.model_dump(),
            "source_profile": source_profile,
            "window_seconds": window_seconds,
            "symbols": SYMBOLS,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
