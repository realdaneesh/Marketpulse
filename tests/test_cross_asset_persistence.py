import asyncio
import sqlite3
import threading

import httpx
import pytest

from marketpulse.analytics.worker import AnalyticsWorker
from marketpulse.api.app import create_app
from marketpulse.cross_asset.config import CrossAssetConfig
from marketpulse.cross_asset.repository import CrossAssetRepository
from marketpulse.cross_asset.worker import CrossAssetWorker
from marketpulse.persistence import migrations
from marketpulse.persistence.sqlite import SCHEMA, TradeRepository


@pytest.fixture
def cross_settings(analytics_settings):
    return analytics_settings.model_copy(
        update={
            "cross_asset": CrossAssetConfig(
                lookback=4,
                min_pairs=3,
                min_coverage=0.75,
                baseline_windows=3,
                min_baseline=3,
                max_lag=1,
            ),
            "cross_asset_batch_size": 2,
        }
    )


async def seed(repository, settings, make_trade, count=16):
    trades = [
        make_trade(
            minute * 60 + tick * 10,
            minute * 4 + tick + 1,
            str(100 + minute % 5 + tick / 10),
            symbol=symbol,
        )
        for minute in range(count)
        for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT")
        for tick in range(4)
    ]
    await repository.insert_batch(trades)
    await AnalyticsWorker(settings).run_once(repository)
    return trades


async def drain(repository, settings):
    worker = CrossAssetWorker(settings)
    while (result := await worker.run_once(repository)).batch_limit_reached:
        pass
    return result


async def test_restart_duplicate_safety_and_bounded_batch(cross_settings, make_trade):
    async with CrossAssetRepository(cross_settings.database_path) as repo:
        await seed(repo, cross_settings, make_trade)
        first = await CrossAssetWorker(cross_settings).run_once(repo)
        assert first.snapshots == 2 and first.batch_limit_reached
        before = await repo.cross_history(cross_settings, 100)
    async with CrossAssetRepository(cross_settings.database_path) as repo:
        await drain(repo, cross_settings)
        history = await repo.cross_history(cross_settings, 100)
        assert len(history) > len(before) and all(row in history for row in before)
        assert len({r.id for r in history}) == len(history)
        assert (await CrossAssetWorker(cross_settings).run_once(repo)).snapshots == 0
        assert (await repo.cross_status(cross_settings)).state == "caught_up"


async def test_slowest_source_horizon_no_early_publication(cross_settings, make_trade):
    async with CrossAssetRepository(cross_settings.database_path) as repo:
        await repo.insert_batch([make_trade(m * 60, m + 1) for m in range(10)])
        await AnalyticsWorker(cross_settings).run_once(repo)
        assert (await CrossAssetWorker(cross_settings).run_once(repo)).snapshots == 0
        assert (await repo.cross_status(cross_settings)).state == "waiting_for_sources"
        assert (await repo.cross_latest(cross_settings)).latest is None


async def test_lagging_source_limits_then_resumes_without_rewriting(cross_settings, make_trade):
    async with CrossAssetRepository(cross_settings.database_path) as repo:
        await seed(repo, cross_settings, make_trade)
        await repo._run(
            lambda: repo.connection.execute(
                "UPDATE analytics_symbol_state "
                "SET finalized_end='2024-01-01T00:08:00.000000+00:00' "
                "WHERE symbol='SOLUSDT'"
            )
        )
        await repo._run(repo.connection.commit)
        await drain(repo, cross_settings)
        rows = await repo.cross_history(cross_settings, 100)
        assert rows[0].window_end.isoformat() == "2024-01-01T00:08:00+00:00"
        await repo._run(
            lambda: repo.connection.execute(
                "UPDATE analytics_symbol_state "
                "SET finalized_end='2024-01-01T00:15:00.000000+00:00' "
                "WHERE symbol='SOLUSDT'"
            )
        )
        await repo._run(repo.connection.commit)
        await drain(repo, cross_settings)
        resumed = await repo.cross_history(cross_settings, 100)
        assert len(resumed) > len(rows) and all(row in resumed for row in rows)


async def test_late_raw_data_cannot_rewrite_relationships(cross_settings, make_trade):
    async with CrossAssetRepository(cross_settings.database_path) as repo:
        await seed(repo, cross_settings, make_trade)
        await drain(repo, cross_settings)
        before = await repo.cross_history(cross_settings, 100)
        await repo.insert_batch([make_trade(20, 90000, "1000000")])
        await AnalyticsWorker(cross_settings).run_once(repo)
        assert (await CrossAssetWorker(cross_settings).run_once(repo)).snapshots == 0
        assert await repo.cross_history(cross_settings, 100) == before
        assert (await repo.cross_status(cross_settings)).sources[0].late_trades == 1


async def test_atomic_result_failure_does_not_advance_checkpoint(cross_settings, make_trade):
    async with CrossAssetRepository(cross_settings.database_path) as repo:
        await seed(repo, cross_settings, make_trade)
        await repo._run(
            lambda: repo.connection.execute(
                "CREATE TRIGGER fail_cross BEFORE INSERT ON cross_snapshots "
                "BEGIN SELECT RAISE(ABORT, 'test failure'); END"
            )
        )
        with pytest.raises(sqlite3.IntegrityError):
            await repo.cross_step(cross_settings)
        status = await repo.cross_status(cross_settings)
        assert status.processed_through is None and status.snapshots == 0
        await repo._run(lambda: repo.connection.execute("DROP TRIGGER fail_cross"))
        assert await repo.cross_step(cross_settings)


async def test_read_snapshot_does_not_block_ingestion(cross_settings, make_trade, monkeypatch):
    import marketpulse.cross_asset.repository as module

    entered, release = threading.Event(), threading.Event()
    original = module.evaluate

    def slow(*args):
        entered.set()
        if not release.wait(5):
            raise RuntimeError("release timeout")
        return original(*args)

    monkeypatch.setattr(module, "evaluate", slow)
    async with CrossAssetRepository(cross_settings.database_path) as repo:
        await seed(repo, cross_settings, make_trade)
        async with TradeRepository(cross_settings.database_path) as writer:
            task = asyncio.create_task(repo.cross_step(cross_settings))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                assert (
                    await asyncio.wait_for(writer.insert_batch([make_trade(2000, 99999)]), 1) == 1
                )
            finally:
                release.set()
                await task


async def test_profile_isolation_and_cold_gap_compaction(cross_settings, make_trade):
    async with CrossAssetRepository(cross_settings.database_path) as repo:
        await seed(repo, cross_settings, make_trade, 8)
        await repo.insert_batch(
            [
                make_trade(60 * 10000 + tick * 60, 1000 + tick, symbol=symbol)
                for tick in range(3)
                for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT")
            ]
        )
        await AnalyticsWorker(cross_settings).run_once(repo)
        await drain(repo, cross_settings)
        rows = await repo.cross_history(cross_settings, 100)
        assert len(rows) < 30
        assert any(row.skipped_intervals > 9000 for row in rows)
        assert rows[0].regime.label == "insufficient_data"
        other = cross_settings.model_copy(
            update={
                "cross_asset": cross_settings.cross_asset.model_copy(update={"min_coverage": 1.0})
            }
        )
        assert (await repo.cross_latest(other)).latest is None
        assert (await repo.cross_status(other)).state == "not_started"


async def test_v2_migration_preserves_all_source_rows(settings):
    with sqlite3.connect(settings.database_path) as db:
        db.executescript(SCHEMA)
        for sql in migrations.STATEMENTS:
            db.execute(sql)
        db.execute("PRAGMA user_version=2")
        db.execute(
            "INSERT INTO trades VALUES "
            "('binance','BTCUSDT',1,'100.123456789','1','2024-01-01T00:00:00.000000+00:00',0)"
        )
        before = db.execute("SELECT * FROM trades").fetchall()
        ledger = db.execute("SELECT * FROM trade_changes").fetchall()
    async with CrossAssetRepository(settings.database_path) as repo:
        assert (
            await repo._run(lambda: repo.connection.execute("PRAGMA user_version").fetchone()[0])
            == 3
        )
        assert (
            await repo._run(
                lambda: [tuple(r) for r in repo.connection.execute("SELECT * FROM trades")]
            )
            == before
        )
        assert (
            await repo._run(
                lambda: [tuple(r) for r in repo.connection.execute("SELECT * FROM trade_changes")]
            )
            == ledger
        )


async def test_v3_migration_failure_rolls_back_v2_intact(settings, monkeypatch):
    with sqlite3.connect(settings.database_path) as db:
        db.executescript(SCHEMA)
        for sql in migrations.STATEMENTS:
            db.execute(sql)
        db.execute("PRAGMA user_version=2")
    monkeypatch.setattr(
        migrations, "CROSS_STATEMENTS", (*migrations.CROSS_STATEMENTS[:1], "INVALID SQL")
    )
    with pytest.raises(sqlite3.OperationalError):
        async with CrossAssetRepository(settings.database_path):
            pass
    with sqlite3.connect(settings.database_path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert (
            db.execute("SELECT name FROM sqlite_master WHERE name='cross_profiles'").fetchone()
            is None
        )


PATHS = ("correlations", "matrix", "breakdowns", "lead-lag", "regimes", "regimes/latest", "status")


async def test_api_empty_and_populated_contracts_compatibility(cross_settings, make_trade):
    app = create_app(cross_settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            for path in PATHS:
                assert (await client.get("/api/cross-asset/" + path)).status_code == 200
            assert (await client.get("/api/cross-asset/matrix")).json()["latest"] is None
            assert (await client.get("/api/cross-asset/status")).json()["state"] == "not_started"
            await seed(app.state.repository, cross_settings, make_trade)
            await drain(app.state.repository, cross_settings)
            matrix = (await client.get("/api/cross-asset/matrix")).json()
            assert matrix["latest"]["pairs"][0]["coefficient"] == pytest.approx(1)
            assert matrix["latest"]["window_end"].endswith("Z")
            assert len((await client.get("/api/cross-asset/correlations?limit=2")).json()) == 2
            lags = (
                await client.get("/api/cross-asset/lead-lag?leader=BTCUSDT&follower=ETHUSDT")
            ).json()
            assert len(lags["analyses"]) == 1
            assert len((await client.get("/api/analytics/latest")).json()) == 3
            assert len((await client.get("/api/trades/recent?limit=10")).json()) == 10
            assert (await client.post("/api/cross-asset/matrix")).status_code == 405


@pytest.mark.parametrize(
    "route",
    [
        "correlations?limit=0",
        "correlations?limit=1001",
        "regimes?limit=no",
        "breakdowns?pair=SOLUSDT-BTCUSDT",
        "lead-lag?leader=BAD",
        "lead-lag?leader=BTCUSDT&follower=BTCUSDT",
    ],
)
async def test_api_rejects_invalid_filters(settings, route):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/cross-asset/" + route)).status_code == 422


async def test_api_database_failure_is_503(settings, monkeypatch):
    app = create_app(settings)

    async def fail(*args):
        raise sqlite3.OperationalError("test-only failure")

    async with app.router.lifespan_context(app):
        monkeypatch.setattr(app.state.repository, "cross_status", fail)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/cross-asset/status")).status_code == 503
