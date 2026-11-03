"""Incremental bounded work; restart-safe state is owned by the repository."""

import asyncio
from dataclasses import dataclass

from marketpulse.config import Settings
from marketpulse.cross_asset.repository import CrossAssetRepository


@dataclass
class CrossPass:
    snapshots: int = 0
    batch_limit_reached: bool = False


class CrossAssetWorker:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def run_once(
        self, repository: CrossAssetRepository, stop: asyncio.Event | None = None
    ) -> CrossPass:
        result = CrossPass()
        for _ in range(self.settings.cross_asset_batch_size):
            if stop and stop.is_set():
                break
            if not await repository.cross_step(self.settings):
                break
            result.snapshots += 1
        else:
            result.batch_limit_reached = True
        return result
