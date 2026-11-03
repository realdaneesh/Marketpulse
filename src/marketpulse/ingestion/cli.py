"""Windows-compatible CLI with signal-driven graceful shutdown."""

import argparse
import asyncio
import logging
import signal
from dataclasses import asdict

from marketpulse.config import Settings
from marketpulse.ingestion.service import IngestionService
from marketpulse.logging import configure_logging

logger = logging.getLogger("marketpulse.ingestion.cli")


async def run(settings: Settings, duration: float | None) -> None:
    """Run until Ctrl+C, SIGTERM, or an optional bounded smoke-test duration."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    previous = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.signal(
            signum,
            lambda *_: loop.call_soon_threadsafe(stop.set),
        )
    timer = loop.call_later(duration, stop.set) if duration is not None else None
    service = IngestionService(settings)
    try:
        await service.run(stop)
        logger.info("session_summary", extra={"fields": asdict(service.stats)})
    finally:
        if timer is not None:
            timer.cancel()
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def main() -> None:
    """Load configuration and start the ingestion process."""
    parser = argparse.ArgumentParser(description="Collect public Binance trades into SQLite")
    parser.add_argument("--duration", type=float, help="Stop gracefully after N seconds")
    args = parser.parse_args()
    if args.duration is not None and args.duration <= 0:
        parser.error("--duration must be positive")
    settings = Settings()
    listener = configure_logging(settings.log_level)
    try:
        asyncio.run(run(settings, args.duration))
    except KeyboardInterrupt:
        pass
    except Exception:
        logger.exception("ingestion_failed")
        raise SystemExit(1) from None
    finally:
        listener.stop()


if __name__ == "__main__":
    main()
