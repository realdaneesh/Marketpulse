"""SQLite operations confined to one worker thread per repository instance."""

import asyncio
import sqlite3
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypeVar

from marketpulse.models import Trade
from marketpulse.persistence.migrations import migrate

T = TypeVar("T")

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trade_id INTEGER NOT NULL,
    price TEXT NOT NULL,
    quantity TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    buyer_maker INTEGER NOT NULL CHECK (buyer_maker IN (0, 1)),
    PRIMARY KEY (exchange, symbol, trade_id)
);
CREATE INDEX IF NOT EXISTS trades_recent ON trades(timestamp DESC, trade_id DESC);
CREATE INDEX IF NOT EXISTS trades_symbol_recent ON trades(symbol, timestamp DESC, trade_id DESC);
"""


class TradeRepository:
    """Own one SQLite connection; all disk I/O runs outside the asyncio loop."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="marketpulse-sqlite")
        self._connection: sqlite3.Connection | None = None

    async def _run(self, function: Callable[[], T]) -> T:
        return await asyncio.get_running_loop().run_in_executor(self._executor, function)

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("repository is not open")
        return self._connection

    def _open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, timeout=5.0)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.executescript(SCHEMA)
        migrate(self.connection)

    async def __aenter__(self) -> "TradeRepository":
        try:
            await self._run(self._open)
        except BaseException:
            await self.close()
            raise
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the connection on its owning thread, then release the worker."""

        def cleanup() -> None:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

        try:
            await self._run(cleanup)
        finally:
            await asyncio.to_thread(self._executor.shutdown, wait=True)

    async def insert_batch(self, trades: Sequence[Trade]) -> int:
        """Commit atomically, ignoring only duplicate exchange/symbol/trade IDs."""
        if not trades:
            return 0
        rows = [
            (
                t.exchange,
                t.symbol,
                t.trade_id,
                str(t.price),
                str(t.quantity),
                t.timestamp.isoformat(timespec="microseconds"),
                int(t.buyer_maker),
            )
            for t in trades
        ]

        def insert() -> int:
            with self.connection:
                cursor = self.connection.executemany(
                    "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(exchange, symbol, trade_id) DO NOTHING",
                    rows,
                )
            # rowcount excludes the new analytics ledger trigger's side effects.
            return cursor.rowcount

        return await self._run(insert)

    async def recent(self, limit: int = 100, symbol: str | None = None) -> list[Trade]:
        """Read committed trades newest first, with deterministic tie breaking."""
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")

        def query() -> list[Trade]:
            sql = "SELECT * FROM trades"
            params: list[str | int] = []
            if symbol is not None:
                sql += " WHERE symbol = ?"
                params.append(symbol)
            sql += " ORDER BY timestamp DESC, trade_id DESC, symbol ASC LIMIT ?"
            params.append(limit)
            rows = self.connection.execute(sql, params).fetchall()
            return [
                Trade.model_validate({**dict(row), "buyer_maker": bool(row["buyer_maker"])})
                for row in rows
            ]

        return await self._run(query)

    async def ping(self) -> None:
        """Probe the database for the API health endpoint."""
        await self._run(lambda: self.connection.execute("SELECT 1").fetchone())
