"""Fixed chronological design and robust, gap-resetting two-sided CUSUM."""

import math
from datetime import datetime
from statistics import median

from marketpulse.research.models import ResearchConfig


def segment(index: int, count: int, embargo: int) -> str:
    train, validation = int(count * 0.6), int(count * 0.8)
    if index < train:
        return "train"
    if index < train + embargo or validation <= index < validation + embargo:
        return "embargo"
    return "validation" if index < validation else "test"


class Cusum:
    """Frozen robust initialization, clipped increments; reset after a flag or gap."""

    def __init__(self, config: ResearchConfig, floor: float):
        self.config, self.floor = config, floor
        self.reset()

    def reset(self):
        self.history = []
        self.recent = []
        self.positive = self.negative = 0.0
        self.last = None
        self.fold = None
        self.center = self.scale = None
        self.count = 0

    def step(self, time: datetime, value: float | None, fold: str, seconds: int):
        if (
            value is None
            or not math.isfinite(value)
            or fold == "embargo"
            or (self.last is not None and (time - self.last).total_seconds() != seconds)
            or (self.fold is not None and fold != self.fold)
        ):
            self.reset()
        if value is None or not math.isfinite(value) or fold == "embargo":
            return None
        self.last, self.fold = time, fold
        self.count += 1
        cfg = self.config
        if self.center is None:
            self.history.append(value)
            if len(self.history) == cfg.initialization:
                self.center = float(median(self.history))
                mad = median(abs(x - self.center) for x in self.history)
                self.scale = max(1.4826 * mad, self.floor)
            return None
        z = max(-cfg.clip, min(cfg.clip, (value - self.center) / self.scale))
        self.positive = max(0.0, self.positive + z - cfg.allowance)
        self.negative = max(0.0, self.negative - z - cfg.allowance)
        self.recent = [*self.recent, value][-cfg.persistence :]
        effect = median(self.recent) - self.center
        positive = effect > 0
        score = self.positive if positive else self.negative
        persistent = all((x - self.center) * (1 if positive else -1) > 0 for x in self.recent)
        if (
            len(self.recent) < cfg.persistence
            or not persistent
            or abs(effect) < cfg.minimum_effect * self.scale
            or score < cfg.threshold
        ):
            return None
        result = dict(
            baseline=self.center,
            scale=self.scale,
            effect=effect,
            cumulative_score=score,
            observations=self.count,
            direction="increase" if positive else "decrease",
        )
        self.reset()
        return result
