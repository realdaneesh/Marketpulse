"""Run bounded historical analytics or poll incrementally; no exchange connection needed."""

import argparse
import asyncio
import logging
import signal

from marketpulse.analytics.worker import AnalyticsWorker
from marketpulse.config import Settings
from marketpulse.logging import configure_logging
from marketpulse.persistence.analytics import AnalyticsRepository

logger = logging.getLogger("marketpulse.analytics.cli")


async def run(settings: Settings, watch: bool) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    handlers = {
        sig: signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
        for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        async with AnalyticsRepository(settings.database_path) as repository:
            worker = AnalyticsWorker(settings)
            while not stop.is_set():
                result = await worker.run_once(repository, stop)
                if result.window_limit_reached:
                    continue
                if not watch:
                    break
                try:
                    await asyncio.wait_for(stop.wait(), settings.analytics_poll_interval)
                except TimeoutError:
                    pass
            latest = await repository.latest(settings.analytics.profile_id, settings.symbols, 1000)
            for item in latest:
                logger.info(
                    "analytics_readiness",
                    extra={"fields": item.model_dump(mode="json", exclude={"evaluation"})},
                )
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process committed trades into statistical analytics"
    )
    parser.add_argument("--watch", action="store_true", help="Poll new commits until Ctrl+C")
    args = parser.parse_args()
    settings = Settings()
    listener = configure_logging(settings.log_level)
    try:
        asyncio.run(run(settings, args.watch))
    except Exception:
        logger.exception("analytics_failed")
        raise SystemExit(1) from None
    finally:
        listener.stop()


if __name__ == "__main__":
    main()
