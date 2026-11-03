import asyncio
import json
import threading
import time

from marketpulse.ingestion.parser import parse_trade
from marketpulse.persistence.sqlite import TradeRepository


async def test_duplicate_key_precision_and_reopen(settings, payload):
    btc = parse_trade(json.dumps(payload))
    eth = parse_trade(json.dumps({**payload, "s": "ETHUSDT"}))
    async with TradeRepository(settings.database_path) as repository:
        assert await repository.insert_batch([btc, btc, eth]) == 2
        assert await repository.insert_batch([btc]) == 0
        rows = await repository.recent()
        assert {row.symbol for row in rows} == {"BTCUSDT", "ETHUSDT"}
        assert await repository.recent(symbol="BTCUSDT") == [btc]
    async with TradeRepository(settings.database_path) as repository:
        assert await repository.insert_batch([btc]) == 0
        assert (await repository.recent(symbol="BTCUSDT"))[0] == btc
    # Windows refuses this rename if the repository still holds the database open.
    settings.database_path.rename(settings.database_path.with_suffix(".closed"))


async def test_recent_ordering_and_limit(settings, payload):
    old = parse_trade(json.dumps(payload))
    new = parse_trade(json.dumps({**payload, "t": 124, "T": payload["T"] + 1}))
    async with TradeRepository(settings.database_path) as repository:
        await repository.insert_batch([new, old])
        assert await repository.recent(limit=1) == [new]
        assert await repository.recent(symbol="SOLUSDT") == []


async def test_database_worker_does_not_block_event_loop(settings):
    main_thread = threading.get_ident()
    started = threading.Event()
    ticks = 0

    def slow_database_operation():
        assert threading.get_ident() != main_thread
        started.set()
        time.sleep(0.1)

    async with TradeRepository(settings.database_path) as repository:
        work = asyncio.create_task(repository._run(slow_database_operation))
        while not work.done():
            await asyncio.sleep(0.005)
            if started.is_set():
                ticks += 1
        await work
    assert ticks >= 3
