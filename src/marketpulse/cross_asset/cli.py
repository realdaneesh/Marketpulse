"""Run cross-asset historical backfill once, or incrementally with --watch."""

import argparse
import asyncio
import signal

from marketpulse.config import Settings
from marketpulse.cross_asset.repository import CrossAssetRepository
from marketpulse.cross_asset.worker import CrossAssetWorker


async def run(settings: Settings, watch: bool) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    handlers = {
        sig: signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
        for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        async with CrossAssetRepository(settings.database_path) as repository:
            worker = CrossAssetWorker(settings)
            while not stop.is_set():
                result = await worker.run_once(repository, stop)
                if result.batch_limit_reached:
                    continue
                print((await repository.cross_status(settings)).model_dump_json())
                if not watch:
                    break
                try:
                    await asyncio.wait_for(stop.wait(), settings.cross_asset_poll_interval)
                except TimeoutError:
                    pass
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Completed-window cross-asset relationship research"
    )
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(Settings(), args.watch))


if __name__ == "__main__":
    main()
