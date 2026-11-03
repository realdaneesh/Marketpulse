import sqlite3

import pytest

from marketpulse.analytics.worker import AnalyticsWorker
from marketpulse.persistence.analytics import AnalyticsRepository
from marketpulse.persistence.sqlite import SCHEMA, TradeRepository


async def test_historical_processing_idempotence_and_stable_alerts(
    analytics_settings, make_windows
):
    config = analytics_settings.analytics
    trades = make_windows()
    async with AnalyticsRepository(analytics_settings.database_path) as repo:
        await repo.insert_batch(list(reversed(trades)))
        worker = AnalyticsWorker(analytics_settings)
        first = await worker.run_once(repo)
        assert first.staged_trades == len(trades)
        assert first.finalized_windows == 8
        events = await repo.events(config.profile_id, 100)
        assert len(events) == 1 and events[0].risk.score == 100
        assert len(await repo.candles(config.profile_id, 100)) == 8
        second = await worker.run_once(repo)
        assert second.staged_trades == second.finalized_windows == 0
        assert await repo.events(config.profile_id, 100) == events
    async with AnalyticsRepository(analytics_settings.database_path) as repo:
        assert (await AnalyticsWorker(analytics_settings).run_once(repo)).staged_trades == 0
        assert await repo.events(config.profile_id, 100) == events


async def test_initial_twenty_seconds_and_per_symbol_watermark(analytics_settings, make_trade):
    trades = [make_trade(0), make_trade(20, 2), make_trade(600, 1, symbol="ETHUSDT")]
    async with AnalyticsRepository(analytics_settings.database_path) as repo:
        await repo.insert_batch(trades)
        result = await AnalyticsWorker(analytics_settings).run_once(repo)
        assert result.finalized_windows == 0
        latest = await repo.latest(
            analytics_settings.analytics.profile_id, ("BTCUSDT", "ETHUSDT"), 10
        )
        assert all(item.status == "insufficient_history" for item in latest)
        assert latest[0].pending_trades == 2
        assert await repo.events(analytics_settings.analytics.profile_id, 10) == []


async def test_lateness_allows_reordering_before_finalization(analytics_settings, make_trade):
    config = analytics_settings.analytics.model_copy(update={"allowed_lateness_seconds": 10})
    settings = analytics_settings.model_copy(update={"analytics": config})
    async with AnalyticsRepository(settings.database_path) as repo:
        await repo.insert_batch([make_trade(50, 2), make_trade(65, 3)])
        worker = AnalyticsWorker(settings)
        assert (await worker.run_once(repo)).finalized_windows == 0
        await repo.insert_batch([make_trade(5, 1), make_trade(70, 4)])
        assert (await worker.run_once(repo)).finalized_windows == 1
        candle = (await repo.candles(config.profile_id, 10))[0]
        assert candle.trade_count == 2 and candle.first_trade_id == 1


async def test_late_data_preserved_but_does_not_rewrite_final_results(
    analytics_settings, make_windows, make_trade
):
    async with AnalyticsRepository(analytics_settings.database_path) as repo:
        await repo.insert_batch(make_windows())
        worker = AnalyticsWorker(analytics_settings)
        await worker.run_once(repo)
        profile = analytics_settings.analytics.profile_id
        before = await repo.candles(profile, 100)
        events = await repo.events(profile, 100)
        await repo.insert_batch([make_trade(10, 1000, "1000000")])
        await worker.run_once(repo)
        assert await repo.candles(profile, 100) == before
        assert await repo.events(profile, 100) == events
        assert (await repo.latest(profile, ("BTCUSDT",), 1))[0].late_trades == 1
        assert (
            await repo._run(
                lambda: repo.connection.execute(
                    "SELECT COUNT(*) FROM trades WHERE trade_id=1000"
                ).fetchone()[0]
            )
            == 1
        )


async def test_missing_intervals_compacted_and_baseline_reset(analytics_settings, make_trade):
    async with AnalyticsRepository(analytics_settings.database_path) as repo:
        await repo.insert_batch(
            [make_trade(0, 1), make_trade(60, 2), make_trade(600, 3), make_trade(660, 4)]
        )
        await AnalyticsWorker(analytics_settings).run_once(repo)
        candles = list(reversed(await repo.candles(analytics_settings.analytics.profile_id, 100)))
        gap = next(c for c in candles if c.quality == "missing")
        assert gap.missing_intervals == 8 and gap.quote_volume is None
        assert candles[-1].quality == "data_gap" and candles[-1].log_return is None
        assert await repo.events(analytics_settings.analytics.profile_id, 100) == []


async def test_trade_id_gap_excludes_window(analytics_settings, make_windows):
    trades = make_windows(count=5, shock_at=None)
    trades = [t for t in trades if t.trade_id != 6]
    async with AnalyticsRepository(analytics_settings.database_path) as repo:
        await repo.insert_batch(trades)
        await AnalyticsWorker(analytics_settings).run_once(repo)
        candles = list(reversed(await repo.candles(analytics_settings.analytics.profile_id, 100)))
        assert candles[1].quality == "data_gap"
        assert candles[2].quality == "observed" and candles[2].log_return is None


async def test_partial_checkpoint_restart_and_no_future_rewrite(analytics_settings, make_windows):
    trades = make_windows()
    config = analytics_settings.analytics
    async with AnalyticsRepository(analytics_settings.database_path) as repo:
        await repo.insert_batch(trades[:24])
        await repo.register(config)
        assert (await repo.stage_page(config, await repo.high_sequence(), 3))[0] == 3
    async with AnalyticsRepository(analytics_settings.database_path) as repo:
        worker = AnalyticsWorker(analytics_settings)
        assert (await worker.run_once(repo)).staged_trades == 21
        before = await repo.candles(config.profile_id, 100)
        await repo.insert_batch(trades[24:])
        await worker.run_once(repo)
        after = await repo.candles(config.profile_id, 100)
        assert all(candle in after for candle in before)
        assert len(await repo.events(config.profile_id, 100)) == 1


async def test_finalization_transaction_rolls_back_on_failure(analytics_settings, make_windows):
    async with AnalyticsRepository(analytics_settings.database_path) as repo:
        await repo.insert_batch(make_windows())
        worker = AnalyticsWorker(analytics_settings)
        original = worker.build

        def fail(*args):
            raise RuntimeError("simulated evaluation failure")

        worker.build = fail
        with pytest.raises(RuntimeError, match="simulated"):
            await worker.run_once(repo)
        assert await repo.candles(analytics_settings.analytics.profile_id, 100) == []
        worker.build = original
        result = await worker.run_once(repo)
        assert result.staged_trades == 0 and result.finalized_windows == 8


async def test_window_limit_continues_without_historical_rescan(analytics_settings, make_windows):
    settings = analytics_settings.model_copy(update={"analytics_max_windows": 2})
    async with AnalyticsRepository(settings.database_path) as repo:
        await repo.insert_batch(make_windows())
        worker = AnalyticsWorker(settings)
        result = await worker.run_once(repo)
        assert result.window_limit_reached and result.finalized_windows == 2
        result = await worker.run_once(repo)
        assert result.staged_trades == 0 and result.finalized_windows == 2


async def test_phase1_migration_preserves_raw_data_and_trigger_counts(settings, make_trade):
    trade = make_trade()
    # Recreate the exact original schema, with no analytics and user_version=0.
    with sqlite3.connect(settings.database_path) as db:
        db.executescript(SCHEMA)
        db.execute(
            "INSERT INTO trades VALUES (?,?,?,?,?,?,?)",
            (
                trade.exchange,
                trade.symbol,
                trade.trade_id,
                str(trade.price),
                str(trade.quantity),
                trade.timestamp.isoformat(timespec="microseconds"),
                int(trade.buyer_maker),
            ),
        )
    async with TradeRepository(settings.database_path) as repo:
        assert await repo.recent() == [trade]
        assert await repo.insert_batch([trade, make_trade(60, 2)]) == 1
        assert await repo.insert_batch([trade]) == 0
        assert (
            await repo._run(lambda: repo.connection.execute("PRAGMA user_version").fetchone()[0])
            == 3
        )
        assert (
            await repo._run(
                lambda: repo.connection.execute("SELECT COUNT(*) FROM trade_changes").fetchone()[0]
            )
            == 2
        )
    async with AnalyticsRepository(settings.database_path) as repo:
        assert len(await repo.recent()) == 2
        assert await repo.high_sequence() == 2
        await repo._run(lambda: repo.connection.execute("VACUUM"))
        assert await repo.high_sequence() == 2


async def test_config_profile_isolation(analytics_settings, make_windows):
    async with AnalyticsRepository(analytics_settings.database_path) as repo:
        await repo.insert_batch(make_windows())
        await AnalyticsWorker(analytics_settings).run_once(repo)
        config2 = analytics_settings.analytics.model_copy(update={"window_seconds": 120})
        settings2 = analytics_settings.model_copy(update={"analytics": config2})
        await AnalyticsWorker(settings2).run_once(repo)
        assert len(await repo.candles(config2.profile_id, 100)) == 4
        assert len(await repo.candles(analytics_settings.analytics.profile_id, 100)) == 8
