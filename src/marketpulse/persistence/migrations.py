"""Transactional additive Phase 2 migration; raw trades are never rebuilt or deleted."""

import sqlite3

from marketpulse.cross_asset.migration import STATEMENTS as CROSS_STATEMENTS

STATEMENTS = (
    """CREATE TABLE trade_changes (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        exchange TEXT NOT NULL, symbol TEXT NOT NULL, trade_id INTEGER NOT NULL,
        timestamp TEXT NOT NULL, UNIQUE(exchange, symbol, trade_id)
    )""",
    """INSERT INTO trade_changes(exchange,symbol,trade_id,timestamp)
        SELECT exchange,symbol,trade_id,timestamp FROM trades ORDER BY rowid""",
    """CREATE TRIGGER trades_capture_insert AFTER INSERT ON trades BEGIN
        INSERT INTO trade_changes(exchange,symbol,trade_id,timestamp)
        VALUES (NEW.exchange,NEW.symbol,NEW.trade_id,NEW.timestamp);
    END""",
    """CREATE TABLE analytics_profiles (
        profile_id TEXT PRIMARY KEY, config_json TEXT NOT NULL, cursor INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE analytics_symbol_state (
        profile_id TEXT NOT NULL, symbol TEXT NOT NULL, max_event TEXT NOT NULL,
        finalized_end TEXT, PRIMARY KEY(profile_id,symbol)
    )""",
    """CREATE TABLE analytics_pending (
        profile_id TEXT NOT NULL, seq INTEGER NOT NULL, exchange TEXT NOT NULL,
        symbol TEXT NOT NULL, trade_id INTEGER NOT NULL, timestamp TEXT NOT NULL,
        window_start TEXT NOT NULL, PRIMARY KEY(profile_id,seq)
    )""",
    """CREATE INDEX analytics_pending_window
        ON analytics_pending(profile_id,symbol,window_start,timestamp,trade_id)""",
    """CREATE TABLE analytics_late_trades (
        profile_id TEXT NOT NULL, seq INTEGER NOT NULL, symbol TEXT NOT NULL,
        timestamp TEXT NOT NULL, finalized_end TEXT NOT NULL, PRIMARY KEY(profile_id,seq)
    )""",
    """CREATE INDEX analytics_late_symbol ON analytics_late_trades(profile_id,symbol)""",
    """CREATE TABLE market_windows (
        id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, symbol TEXT NOT NULL,
        window_start TEXT NOT NULL, window_end TEXT NOT NULL, quality TEXT NOT NULL,
        candle_json TEXT NOT NULL, risk_json TEXT NOT NULL,
        UNIQUE(profile_id,symbol,window_start)
    )""",
    """CREATE INDEX market_windows_recent
        ON market_windows(profile_id,window_start DESC,symbol)""",
    """CREATE INDEX market_windows_symbol
        ON market_windows(profile_id,symbol,window_start DESC)""",
    """CREATE TABLE detector_results (
        window_id TEXT NOT NULL, detector TEXT NOT NULL, result_json TEXT NOT NULL,
        PRIMARY KEY(window_id,detector)
    )""",
    """CREATE TABLE anomaly_events (
        id TEXT PRIMARY KEY, window_id TEXT NOT NULL UNIQUE, profile_id TEXT NOT NULL,
        symbol TEXT NOT NULL, window_start TEXT NOT NULL, window_end TEXT NOT NULL,
        score REAL NOT NULL, event_json TEXT NOT NULL
    )""",
    """CREATE INDEX anomaly_events_recent
        ON anomaly_events(profile_id,window_start DESC,symbol)""",
    """CREATE INDEX anomaly_events_symbol
        ON anomaly_events(profile_id,symbol,window_start DESC)""",
)


def migrate(connection: sqlite3.Connection) -> None:
    """Install once under a write lock, atomically backfilling the insertion ledger.

    A trigger captures inserts even from the Phase 1 collector. Explicit sequence
    IDs remain stable across VACUUM, unlike an unaliased trades.rowid checkpoint.
    """
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > 4:
            raise RuntimeError("database schema is newer than this MarketPulse version")
        if version < 2:
            for statement in STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version=2")
        if version < 3:
            for statement in CROSS_STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version=3")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
