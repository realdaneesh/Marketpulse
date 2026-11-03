"""Finite historical passes and restart-safe incremental analytics orchestration."""

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from marketpulse.analytics.aggregation import CandleAccumulator, missing_candle
from marketpulse.analytics.detectors import evaluate_detectors
from marketpulse.analytics.models import Candle, Evaluation
from marketpulse.analytics.scoring import combine_results
from marketpulse.config import Settings
from marketpulse.models import Trade
from marketpulse.persistence.analytics import AnalyticsRepository

logger = logging.getLogger(__name__)


@dataclass
class PassResult:
    staged_trades: int = 0
    finalized_windows: int = 0
    target_sequence: int = 0
    window_limit_reached: bool = False


class AnalyticsWorker:
    """One worker can process all persisted symbols under a versioned analytics policy."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.config = settings.analytics

    def build(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        trades: Iterable[Trade],
        history: list[Candle],
        gap: bool,
    ) -> Evaluation:
        """Pure window evaluation called on the repository worker thread."""
        previous = history[-1] if history else None
        if gap:
            candle = missing_candle(symbol, start, end, self.config.window_seconds)
        else:
            accumulator = CandleAccumulator(symbol, start, self.config.window_seconds)
            for trade in trades:
                accumulator.add(trade)
            quality = "observed"
            if previous is None:
                quality = "partial_start"
            elif (
                previous.quality == "missing"
                or previous.window_end != start
                or (
                    previous.last_trade_id is not None
                    and accumulator.first_id is not None
                    and accumulator.first_id != previous.last_trade_id + 1
                )
            ):
                quality = "data_gap"
            if (
                accumulator.first_id is not None
                and accumulator.last_id is not None
                and accumulator.last_id - accumulator.first_id + 1 != accumulator.count
            ):
                quality = "data_gap"
            candle = accumulator.finish(previous, quality)
        detectors = evaluate_detectors(candle, history, self.config)
        return Evaluation(
            candle=candle, detectors=detectors, risk=combine_results(detectors, self.config)
        )

    async def run_once(
        self, repository: AnalyticsRepository, stop: asyncio.Event | None = None
    ) -> PassResult:
        """Consume a fixed high-sequence snapshot before finalizing any of its windows.

        A restart can resume staging. No window is finalized while part of the
        captured snapshot is unread, so insertion-order variation within it is safe.
        """
        await repository.register(self.config)
        result = PassResult(target_sequence=await repository.high_sequence())
        while stop is None or not stop.is_set():
            count, cursor = await repository.stage_page(
                self.config,
                result.target_sequence,
                self.settings.analytics_page_size,
            )
            result.staged_trades += count
            if cursor >= result.target_sequence:
                break
        else:
            return result
        for _ in range(self.settings.analytics_max_windows):
            if stop is not None and stop.is_set():
                break
            if not await repository.finalize_next(self.config, self.build):
                break
            result.finalized_windows += 1
        else:
            result.window_limit_reached = True
        logger.info(
            "analytics_pass",
            extra={
                "fields": {
                    **vars(result),
                    "profile_id": self.config.profile_id,
                }
            },
        )
        return result
