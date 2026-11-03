import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager

import pytest
from websockets.exceptions import ConnectionClosedOK
from websockets.frames import Close

from marketpulse.ingestion.service import IngestionService, backoff_delay
from marketpulse.persistence.sqlite import TradeRepository


class MockSocket:
    def __init__(self, messages, exhausted):
        self.messages = iter(messages)
        self.exhausted = exhausted

    async def recv(self):
        try:
            return next(self.messages)
        except StopIteration:
            self.exhausted.set()
            await asyncio.Future()


async def test_mocked_pipeline_reconnect_malformed_duplicates_shutdown(settings, payload):
    stop = asyncio.Event()
    attempts = []
    closed = []
    messages = [
        "bad JSON",
        json.dumps(payload),
        json.dumps(payload),
        json.dumps({**payload, "s": "ETHUSDT"}),
        json.dumps({"stream": "solusdt@trade", "data": {**payload, "s": "SOLUSDT"}}),
        json.dumps({**payload, "s": "XRPUSDT"}),
    ]

    @asynccontextmanager
    async def connector(uri):
        attempts.append(uri)
        if len(attempts) == 1:
            raise OSError("simulated network failure")
        try:
            yield MockSocket(messages, stop)
        finally:
            closed.append(True)

    service = IngestionService(settings, connector)
    await asyncio.wait_for(service.run(stop), timeout=3)
    assert attempts == [settings.stream_url] * 2
    assert "btcusdt@trade/ethusdt@trade/solusdt@trade" in attempts[0]
    assert closed == [True]
    assert service.stats.received == 4
    assert service.stats.inserted == 3
    assert service.stats.duplicates == 1
    assert service.stats.malformed == 2
    assert service.stats.reconnects == 1
    async with TradeRepository(settings.database_path) as repository:
        assert {t.symbol for t in await repository.recent()} == set(settings.symbols)


async def test_timer_flush_and_cancel_drain(settings, payload, monkeypatch):
    exhausted = asyncio.Event()
    committed = asyncio.Event()
    original_insert = TradeRepository.insert_batch

    async def track_commit(self, batch):
        count = await original_insert(self, batch)
        committed.set()
        return count

    monkeypatch.setattr(TradeRepository, "insert_batch", track_commit)
    settings = settings.model_copy(update={"batch_size": 100})

    @asynccontextmanager
    async def connector(uri):
        yield MockSocket([json.dumps(payload)], exhausted)

    service = IngestionService(settings, connector)
    task = asyncio.create_task(service.run(asyncio.Event()))
    try:
        await asyncio.wait_for(exhausted.wait(), 2)
        await asyncio.wait_for(committed.wait(), 2)
        async with TradeRepository(settings.database_path) as repository:
            assert len(await repository.recent()) == 1
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_cancel_flushes_partial_batch(settings, payload):
    exhausted = asyncio.Event()
    settings = settings.model_copy(update={"batch_size": 100, "flush_interval": 60})

    @asynccontextmanager
    async def connector(uri):
        yield MockSocket([json.dumps(payload)], exhausted)

    service = IngestionService(settings, connector)
    task = asyncio.create_task(service.run(asyncio.Event()))
    await asyncio.wait_for(exhausted.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with TradeRepository(settings.database_path) as repository:
        assert len(await repository.recent()) == 1


async def test_writer_failure_stops_full_queue_without_hanging(settings, payload, monkeypatch):
    async def fail(self, batch):
        raise sqlite3.OperationalError("simulated disk failure")

    monkeypatch.setattr(TradeRepository, "insert_batch", fail)

    @asynccontextmanager
    async def connector(uri):
        yield MockSocket([json.dumps(payload)] * 100, asyncio.Event())

    service = IngestionService(settings, connector)
    with pytest.raises(sqlite3.OperationalError, match="disk failure"):
        await asyncio.wait_for(service.run(asyncio.Event()), timeout=2)


async def test_stop_interrupts_backoff(settings):
    attempted = asyncio.Event()
    settings = settings.model_copy(update={"reconnect_base": 60, "reconnect_max": 60})

    @asynccontextmanager
    async def connector(uri):
        attempted.set()
        raise OSError("offline")
        yield  # pragma: no cover

    stop = asyncio.Event()
    task = asyncio.create_task(IngestionService(settings, connector).run(stop))
    await asyncio.wait_for(attempted.wait(), 2)
    stop.set()
    await asyncio.wait_for(task, 2)


@pytest.mark.parametrize(
    "failure",
    [
        OSError("connection reset"),
        TimeoutError(),
        ConnectionClosedOK(Close(1000, ""), Close(1000, ""), True),
    ],
)
async def test_reconnect_after_established_connection(settings, payload, failure):
    stop = asyncio.Event()
    attempts = 0

    class DisconnectedSocket:
        async def recv(self):
            raise failure

    @asynccontextmanager
    async def connector(uri):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            yield DisconnectedSocket()
        else:
            yield MockSocket([json.dumps(payload)], stop)

    service = IngestionService(settings, connector)
    await asyncio.wait_for(service.run(stop), 2)
    assert attempts == 2
    assert service.stats.reconnects == 1
    assert service.stats.inserted == 1


@pytest.mark.parametrize("attempt,low,high", [(0, 0.5, 1), (1, 1, 2), (6, 30, 60), (10000, 30, 60)])
def test_backoff_is_capped_and_jittered(attempt, low, high):
    values = {backoff_delay(attempt, 1, 60) for _ in range(20)}
    assert all(low <= value <= high for value in values)
    assert len(values) > 1
