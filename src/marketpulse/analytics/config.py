"""Versioned, validated analytics policy; policy changes get distinct result IDs."""

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DetectorName = Literal["volume", "volatility", "imbalance", "price_shock"]
DETECTORS: tuple[DetectorName, ...] = ("volume", "volatility", "imbalance", "price_shock")


class AnalyticsConfig(BaseModel):
    """Environment overrides use MARKETPULSE_ANALYTICS__FIELD_NAME."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    algorithm_version: Literal["v1"] = "v1"
    window_seconds: int = Field(default=60, ge=1, le=86400)
    allowed_lateness_seconds: int = Field(default=10, ge=0, le=86400)
    history_size: int = Field(default=60, ge=2, le=10000)
    min_history: int = Field(default=20, ge=2, le=10000)
    min_imbalance_trades: int = Field(default=20, ge=2)
    min_imbalance_quote_volume: float = Field(default=1000, gt=0)
    min_absolute_imbalance: float = Field(default=0.8, gt=0, le=1)
    relative_scale_floor: float = Field(default=0.01, gt=0, le=1)
    thresholds: dict[DetectorName, float] = Field(
        default_factory=lambda: dict.fromkeys(DETECTORS, 3.5)
    )
    scale_floors: dict[DetectorName, float] = Field(
        default_factory=lambda: {
            "volume": 1.0,
            "volatility": 1e-6,
            "imbalance": 0.01,
            "price_shock": 1e-6,
        }
    )
    weights: dict[DetectorName, float] = Field(
        default_factory=lambda: dict.fromkeys(DETECTORS, 1.0)
    )
    required_detectors: tuple[DetectorName, ...] = DETECTORS
    alert_threshold: float = Field(default=50, gt=0, le=100)

    @model_validator(mode="after")
    def validate_policy(self) -> "AnalyticsConfig":
        import math

        if self.min_history > self.history_size:
            raise ValueError("min_history cannot exceed history_size")
        for name in ("thresholds", "scale_floors", "weights"):
            mapping = getattr(self, name)
            if set(mapping) != set(DETECTORS):
                raise ValueError(f"{name} must specify all four detectors")
            if any(not math.isfinite(v) or v <= 0 for v in mapping.values()):
                raise ValueError(f"{name} values must be finite and positive")
        if not math.isfinite(sum(self.weights.values())):
            raise ValueError("sum of weights must be finite")
        if not self.required_detectors or len(set(self.required_detectors)) != len(
            self.required_detectors
        ):
            raise ValueError("required_detectors must be nonempty and unique")
        return self

    @property
    def profile_id(self) -> str:
        """Hash the complete statistical policy, independently of operational page sizes."""
        import json

        encoded = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()[:24]
