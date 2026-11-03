import asyncio
import sqlite3
import threading

import pytest

from marketpulse.analytics.worker import AnalyticsWorker
from marketpulse.persistence import migrations
from marketpulse.persistence.analytics import AnalyticsRepository
from marketpulse.persistence.backup import backup_database
from marketpulse.persistence.sqlite import TradeRepository


async def test_aggregation_does_not_hold_ingestion_write_lock(
    analytics_settings, make_windows, make_trade
):
    entered = threading.Event()
    release = threading.Event()
    config = analytics_settings.analytics
    worker = AnalyticsWorker(analytics_settings)
    original = worker.build

    def slow_build(*args):
        entered.set()
        if not release.wait(5):
            raise RuntimeError("test failed to release aggregator")
        return original(*args)

    async with AnalyticsRepository(analytics_settings.database_path) as analytics:
        await analytics.insert_batch(make_windows())
        await analytics.register(config)
        await analytics.stage_page(config, await analytics.high_sequence(), 1000)
        async with TradeRepository(analytics_settings.database_path) as ingestion:
            task = asyncio.create_task(analytics.finalize_next(config, slow_build))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                assert (
                    await asyncio.wait_for(ingestion.insert_batch([make_trade(600, 100)]), 1) == 1
                )
            finally:
                release.set()
                await task


async def test_result_write_failure_rolls_back_entire_window(analytics_settings, make_windows):
    async with AnalyticsRepository(analytics_settings.database_path) as repo:
        await repo.insert_batch(make_windows())
        await repo._run(
            lambda: repo.connection.execute(
                "CREATE TRIGGER fail_result BEFORE INSERT ON detector_results "
                "BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END"
            )
        )
        worker = AnalyticsWorker(analytics_settings)
        with pytest.raises(sqlite3.IntegrityError, match="simulated"):
            await worker.run_once(repo)
        assert await repo.candles(analytics_settings.analytics.profile_id, 100) == []
        assert (await repo.latest(analytics_settings.analytics.profile_id, ("BTCUSDT",), 1))[
            0
        ].finalized_through is None
        await repo._run(lambda: repo.connection.execute("DROP TRIGGER fail_result"))
        assert (await worker.run_once(repo)).finalized_windows == 8


async def test_migration_failure_is_atomic(settings, monkeypatch):
    original = migrations.STATEMENTS
    monkeypatch.setattr(migrations, "STATEMENTS", (*original[:2], "INVALID SQL"))
    with pytest.raises(sqlite3.OperationalError):
        async with TradeRepository(settings.database_path):
            pass
    with sqlite3.connect(settings.database_path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0
        assert (
            db.execute("SELECT name FROM sqlite_master WHERE name='trade_changes'").fetchone()
            is None
        )
    monkeypatch.setattr(migrations, "STATEMENTS", original)
    async with TradeRepository(settings.database_path) as repo:
        assert await repo.recent() == []


async def test_backup_preserves_source_and_refuses_overwrite(settings, make_trade, tmp_path):
    destination = tmp_path / "local" / "backup.sqlite3"
    async with TradeRepository(settings.database_path) as source:
        await source.insert_batch([make_trade()])
        await asyncio.to_thread(backup_database, settings.database_path, destination)
        assert len(await source.recent()) == 1
        with pytest.raises(FileExistsError):
            await asyncio.to_thread(backup_database, settings.database_path, destination)
    async with TradeRepository(destination) as backup:
        assert len(await backup.recent()) == 1


def test_nested_analytics_environment(monkeypatch):
    from marketpulse.config import Settings

    monkeypatch.setenv("MARKETPULSE_ANALYTICS__WINDOW_SECONDS", "30")
    monkeypatch.setenv("MARKETPULSE_ANALYTICS__MIN_HISTORY", "5")
    settings = Settings(_env_file=None)
    assert settings.analytics.window_seconds == 30 and settings.analytics.min_history == 5
