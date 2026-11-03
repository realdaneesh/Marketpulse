"""Bounded, supervised WebSocket ingestion with asynchronous batched persistence."""

import asyncio
import logging
import random
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

from marketpulse.config import Settings
from marketpulse.ingestion.parser import MalformedMessage, parse_trade
from marketpulse.models import Trade
from marketpulse.persistence.sqlite import TradeRepository

logger = logging.getLogger(__name__)
trade_logger = logging.getLogger("marketpulse.trades")


class TradeSocket(Protocol):
    async def recv(self) -> str | bytes: ...


Connector = Callable[[str], AbstractAsyncContextManager[TradeSocket]]


@dataclass
class IngestionStats:
    """Process-local counters; received includes duplicate messages."""

    received: int = 0
    malformed: int = 0
    inserted: int = 0
    duplicates: int = 0
    reconnects: int = 0


def backoff_delay(attempt: int, base: float, maximum: float) -> float:
    """Capped exponential backoff with equal jitter and a positive lower bound."""
    ceiling = min(maximum, base * 2 ** min(attempt, 30))
    return random.uniform(ceiling / 2, ceiling)


class IngestionService:
    """Run one reader and one writer; stop the reader before draining queued trades."""

    def __init__(self, settings: Settings, connector: Connector | None = None) -> None:
        self.settings = settings
        self.connector = connector or self._connect
        self.stats = IngestionStats()
        self.queue: asyncio.Queue[Trade | None] = asyncio.Queue(maxsize=settings.queue_size)

    def _connect(self, uri: str) -> AbstractAsyncContextManager[TradeSocket]:
        return connect(
            uri,
            open_timeout=self.settings.open_timeout,
            close_timeout=5,
            ping_interval=20,
            ping_timeout=20,
            max_size=65536,
            max_queue=32,
        )

    async def run(self, stop: asyncio.Event) -> None:
        """Collect until signalled; writer failures terminate collection visibly."""
        async with TradeRepository(self.settings.database_path) as repository:
            reader = asyncio.create_task(self._read(), name="trade-reader")
            writer = asyncio.create_task(self._write(repository), name="trade-writer")
            stopper = asyncio.create_task(stop.wait(), name="ingestion-stop")
            try:
                done, _ = await asyncio.wait(
                    (reader, writer, stopper),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in (writer, reader):
                    if task in done:
                        task.result()
            finally:
                reader.cancel()
                stopper.cancel()
                await asyncio.gather(reader, stopper, return_exceptions=True)
                # Watch the writer while enqueueing the sentinel: a failing writer
                # must never leave shutdown blocked behind a full queue.
                if not writer.done():
                    sentinel = asyncio.create_task(self.queue.put(None))
                    try:
                        await asyncio.wait((sentinel, writer), return_when=asyncio.FIRST_COMPLETED)
                    finally:
                        if not sentinel.done():
                            sentinel.cancel()
                        await asyncio.gather(sentinel, return_exceptions=True)
                await writer
                logger.info("ingestion_stopped", extra={"fields": vars(self.stats)})

    async def _read(self) -> None:
        attempt = 0
        loop = asyncio.get_running_loop()
        while True:
            connected_at: float | None = None
            try:
                async with self.connector(self.settings.stream_url) as socket:
                    connected_at = loop.time()
                    logger.info(
                        "websocket_connected",
                        extra={
                            "fields": {
                                "symbols": self.settings.symbols,
                            }
                        },
                    )
                    while True:
                        message = await asyncio.wait_for(
                            socket.recv(),
                            timeout=self.settings.receive_timeout,
                        )
                        try:
                            trade = parse_trade(message)
                            if trade.symbol not in self.settings.symbols:
                                raise MalformedMessage("unsubscribed symbol")
                        except MalformedMessage:
                            self.stats.malformed += 1
                            # Log counts, never arbitrary remote payloads. Rate limit
                            # corrupt-message storms to keep logs useful and bounded.
                            if self.stats.malformed <= 5 or self.stats.malformed % 100 == 0:
                                logger.warning(
                                    "malformed_trade",
                                    extra={
                                        "fields": {
                                            "malformed_count": self.stats.malformed,
                                        }
                                    },
                                )
                            continue
                        await self.queue.put(trade)
                        self.stats.received += 1
                        if self.settings.display_trades:
                            trade_logger.info(
                                "%s | %-8s | %-4s | price=%s | quantity=%s | id=%s",
                                trade.timestamp.isoformat(timespec="milliseconds"),
                                trade.symbol,
                                trade.aggressor_side.upper(),
                                trade.price,
                                trade.quantity,
                                trade.trade_id,
                            )
            except (OSError, TimeoutError, ConnectionClosed, InvalidHandshake) as exc:
                if (
                    connected_at is not None
                    and loop.time() - connected_at >= self.settings.stable_connection_seconds
                ):
                    attempt = 0
                delay = backoff_delay(
                    attempt, self.settings.reconnect_base, self.settings.reconnect_max
                )
                attempt += 1
                self.stats.reconnects += 1
                logger.warning(
                    "websocket_reconnect",
                    extra={
                        "fields": {
                            "error_type": type(exc).__name__,
                            "reason": str(exc),
                            "attempt": attempt,
                            "delay_seconds": round(delay, 3),
                        }
                    },
                )
                await asyncio.sleep(delay)

    async def _write(self, repository: TradeRepository) -> None:
        batch: list[Trade] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.flush_interval

        async def flush() -> None:
            if not batch:
                return
            inserted = await repository.insert_batch(batch)
            self.stats.inserted += inserted
            self.stats.duplicates += len(batch) - inserted
            logger.debug(
                "batch_committed",
                extra={
                    "fields": {
                        "inserted": inserted,
                        "duplicates": len(batch) - inserted,
                    }
                },
            )
            batch.clear()

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                await flush()
                deadline = loop.time() + self.settings.flush_interval
                continue
            try:
                trade = await asyncio.wait_for(self.queue.get(), timeout=remaining)
            except TimeoutError:
                continue
            if trade is None:
                await flush()
                return
            batch.append(trade)
            if len(batch) >= self.settings.batch_size:
                await flush()
                deadline = loop.time() + self.settings.flush_interval
