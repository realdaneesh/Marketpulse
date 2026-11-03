"""Explicitly synthetic fixtures: these are mechanics tests, not market discoveries."""

import json
import random
import sqlite3
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from marketpulse.analytics.config import AnalyticsConfig
from marketpulse.analytics.worker import AnalyticsWorker
from marketpulse.api.app import create_app
from marketpulse.cross_asset.config import SYMBOLS, CrossAssetConfig
from marketpulse.cross_asset.repository import CrossAssetRepository
from marketpulse.cross_asset.worker import CrossAssetWorker
from marketpulse.research import migration
from marketpulse.research.cli import manifest
from marketpulse.research.design import Cusum, segment
from marketpulse.research.models import ResearchConfig
from marketpulse.research.reliability import adjust, counts, sequence
from marketpulse.research.source import capture, fingerprint, tasks
from marketpulse.research.worker import prepare, step

START = datetime(2024, 1, 1, tzinfo=UTC)


@pytest.fixture
async def research_source(settings, make_trade):
    settings = settings.model_copy(
        update={
            "analytics": AnalyticsConfig(min_history=3, history_size=6, allowed_lateness_seconds=0),
            "cross_asset": CrossAssetConfig(
                lookback=12, min_pairs=6, baseline_windows=5, min_baseline=3, max_lag=2
            ),
        }
    )
    async with CrossAssetRepository(settings.database_path) as repo:
        trades = [
            make_trade(
                minute * 60 + tick * 20,
                minute * 2 + tick + 1,
                price=str(100 + (minute % 7) * 0.3 + tick * 0.01),
                quantity="100" if minute >= 45 else "1",
                symbol=symbol,
            )
            for minute in range(100)
            for symbol in SYMBOLS
            for tick in range(2)
        ]
        await repo.insert_batch(trades)
        await AnalyticsWorker(settings).run_once(repo)
        while (await CrossAssetWorker(settings).run_once(repo)).batch_limit_reached:
            pass
    return settings


def setup_store(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA user_version=3")
    migration.migrate(db)
    db.close()


def run(settings, store, batch=17):
    state = prepare(
        store,
        settings.database_path,
        settings.analytics.profile_id,
        settings.cross_asset.profile_id(settings.analytics.profile_id, 60),
        START,
        START + timedelta(minutes=99),
        ResearchConfig(),
    )
    while state.state not in ("complete", "failed"):
        state = step(store, state.id, batch)
    return state


async def test_replay_equivalence_restart_idempotence_preserves_source(research_source, tmp_path):
    settings = research_source
    before = manifest(settings.database_path)
    store = tmp_path / "research.sqlite3"
    setup_store(store)
    state = run(settings, store, batch=7)
    assert state.state == "complete" and state.discrepancies == 0
    assert state.cursor == state.total == 395
    assert step(store, state.id) == state
    assert run(settings, store, batch=128) == state
    assert manifest(settings.database_path) == before
    second = tmp_path / "second.sqlite3"
    setup_store(second)
    other = run(settings, second, batch=128)
    assert other.id == state.id and other.fingerprint == state.fingerprint
    with sqlite3.connect(store) as a, sqlite3.connect(second) as b:
        assert (
            a.execute("SELECT results_json FROM research_experiments").fetchone()
            == b.execute("SELECT results_json FROM research_experiments").fetchone()
        )
        results = json.loads(
            a.execute("SELECT results_json FROM research_experiments").fetchone()[0]
        )
    assert all(
        s["status"] == "insufficient_data" and s["p_value"] is None for s in results["sequences"]
    )
    assert results["change_points"]
    assert all(d["validation"] == "exploratory" for d in results["discoveries"])
    assert any(m["warmup_excluded"] for m in results["metrics"])


async def test_discrepancies_are_recorded_not_corrected(research_source, tmp_path):
    s = research_source
    with sqlite3.connect(s.database_path) as db:
        row = db.execute(
            "SELECT window_id,detector,result_json FROM detector_results LIMIT 1"
        ).fetchone()
        value = json.loads(row[2])
        value["explanation"] = "synthetic corrupted persisted evidence"
        db.execute(
            "UPDATE detector_results SET result_json=? WHERE window_id=? AND detector=?",
            (json.dumps(value), row[0], row[1]),
        )
    before = manifest(s.database_path)
    store = tmp_path / "store.db"
    setup_store(store)
    assert run(s, store).discrepancies == 1
    assert manifest(s.database_path) == before


async def test_capture_rejects_future_off_grid_and_naive_ranges(research_source):
    s = research_source
    for start, end in (
        (START, START + timedelta(minutes=101)),
        (START + timedelta(seconds=1), START + timedelta(minutes=20)),
        (START.replace(tzinfo=None), START + timedelta(minutes=20)),
    ):
        with pytest.raises(ValueError):
            capture(s.database_path, s.analytics.profile_id, None, start, end, ResearchConfig())


async def test_replay_has_no_future_leakage(research_source):
    from marketpulse.research.replay import replay

    s = research_source
    inputs = capture(
        s.database_path,
        s.analytics.profile_id,
        None,
        START,
        START + timedelta(minutes=99),
        ResearchConfig(),
    )
    kind, row = tasks(inputs)[40]
    result = replay(kind, row, inputs)
    future = json.loads(json.dumps(inputs))
    for candle in future["candles"]:
        if candle["window_start"] > row["window_end"]:
            value = json.loads(candle["candle_json"])
            value["quote_volume"] = "999999999"
            candle["candle_json"] = json.dumps(value)
    assert replay(kind, row, future) == result
    assert fingerprint(inputs) != fingerprint(future)


def test_chronological_splits_and_embargo():
    folds = [segment(i, 1000, 125) for i in range(1000)]
    assert folds[:600] == ["train"] * 600
    assert folds[600:725] == ["embargo"] * 125
    assert folds[725:800] == ["validation"] * 75
    assert folds[800:925] == ["embargo"] * 125
    assert folds[925:] == ["test"] * 75


async def test_cross_replay_does_not_use_future_baselines(research_source):
    from marketpulse.research.replay import replay

    s = research_source
    inputs = capture(
        s.database_path,
        s.analytics.profile_id,
        s.cross_asset.profile_id(s.analytics.profile_id, 60),
        START,
        START + timedelta(minutes=99),
        ResearchConfig(),
    )
    row = inputs["snapshots"][20]
    expected = replay("cross", row, inputs)
    future = json.loads(json.dumps(inputs))
    for snapshot in future["snapshots"]:
        if snapshot["window_end"] > row["window_end"]:
            value = json.loads(snapshot["result_json"])
            for pair in value["pairs"]:
                pair["coefficient"] = -0.999
            snapshot["result_json"] = json.dumps(value)
    assert replay("cross", row, future) == expected


def test_test_period_cannot_tune_training_or_sensitivity():
    from marketpulse.research.analysis import analyze

    inputs = dict(
        seconds=60,
        start=START.isoformat(),
        end=(START + timedelta(minutes=1000)).isoformat(),
        source_config=dict(
            history_size=60, min_imbalance_trades=20, min_imbalance_quote_volume=1000
        ),
        cross_config=None,
    )
    rows = []
    for i in range(1000):
        rows.append(
            dict(
                kind="candle",
                time=(START + timedelta(minutes=i + 1)).isoformat(),
                segment=segment(i, 1000, 61),
                entity="BTCUSDT",
                source_id=str(i),
                candle=dict(
                    quality="observed",
                    quote_volume="10000",
                    trade_count=100,
                    realized_volatility=0.001,
                    signed_imbalance=0.1,
                ),
                results=[
                    dict(detector=name, status="ready", is_anomaly=False, anomaly_score=0)
                    for name in ("volume", "volatility", "imbalance", "price_shock")
                ],
            )
        )
    original = analyze("0" * 64, rows, inputs, ResearchConfig())
    changed = json.loads(json.dumps(rows))
    for row in changed:
        if row["segment"] == "test":
            row["candle"]["quote_volume"] = "999999999"
            row["results"][0]["is_anomaly"] = True
    later = analyze("0" * 64, changed, inputs, ResearchConfig())
    assert original.sensitivity.keys() == later.sensitivity.keys()
    for variant in (
        "primary_development",
        "longer_initialization",
        "higher_threshold",
        "post_gap_guard",
    ):
        assert original.sensitivity[variant] == later.sensitivity[variant]
    assert [s for s in original.sequences if s.segment != "test"] == [
        s for s in later.sequences if s.segment != "test"
    ]
    assert [m for m in original.metrics if m.segment == "train"] == [
        m for m in later.metrics if m.segment == "train"
    ]


def test_cusum_warmup_effect_and_reset():
    cfg = ResearchConfig(initialization=10)
    engine = Cusum(cfg, 0.01)
    for i in range(10):
        assert engine.step(START + timedelta(minutes=i), 1, "train", 60) is None
    found = [engine.step(START + timedelta(minutes=10 + i), 2, "train", 60) for i in range(3)]
    assert found[-1]["effect"] == 1 and found[-1]["baseline"] == 1
    assert engine.step(START + timedelta(minutes=14), 2, "train", 60) is None
    assert engine.step(START + timedelta(minutes=15), None, "train", 60) is None
    assert len(engine.history) == 0
    engine.step(START + timedelta(minutes=16), 1, "train", 60)
    engine.step(START + timedelta(minutes=17), 1, "test", 60)
    assert engine.history == [1]
    engine.step(START + timedelta(minutes=19), 1, "test", 60)
    assert engine.history == [1]


def test_episode_grouping_simultaneous_order_and_no_double_count():
    a = [False, True, True, True, False, False, True, False, False, False]
    b = [False, True, True, False, False, False, False, True, True, False]
    n, hits, _, _, na, nb, simultaneous = counts(a, b, 2)
    assert (n, hits, na, nb, simultaneous) == (2, 1, 2, 2, 1)
    assert counts([True] * 10, [True] * 10, 2)[4:] == (0, 0, 0)


def test_bh_and_by_adjustment_preserves_full_family():
    assert adjust([0.01, 0.04, 0.03], dependent=False) == pytest.approx([0.03, 0.04, 0.04])
    assert adjust([0.01, None], dependent=False) == [0.02, None]
    assert adjust([0.01, 0.04, 0.03])[0] > 0.03
    with pytest.raises(ValueError):
        adjust([-0.1])


def test_sequence_bootstrap_and_null_reproducibility():
    rng = random.Random(41)
    a = [False] * 1920
    b = [False] * 1920
    for i in range(5, 1915, 13):
        a[i] = True
        if rng.random() < 0.8:
            b[i + 1] = True
    config = ResearchConfig(block_length=120)
    first = sequence("BTCUSDT", "ETHUSDT", "train", [(a, b)], 1920, config, 61)
    assert first == sequence("BTCUSDT", "ETHUSDT", "train", [(a, b)], 1920, config, 61)
    assert first.status == "exploratory" and first.interval[0] > 0 and first.effect > 0
    assert first.p_value is not None and first.blocks == 16
    short = sequence("BTCUSDT", "ETHUSDT", "test", [(a[:40], b[:40])], 40, config, 61)
    assert short.status == "insufficient_data" and short.interval is None and short.p_value is None


def test_sequence_does_not_bridge_gaps():
    runs = [([False] * 60, [False] * 60)] * 10
    result = sequence("BTCUSDT", "ETHUSDT", "train", runs, 600, ResearchConfig(), 61)
    assert result.blocks == 0 and result.coverage == 0 and result.p_value is None


async def test_migration_preserves_all_original_tables_and_is_idempotent(research_source):
    path = research_source.database_path
    before = manifest(path)
    with sqlite3.connect(path) as db:
        migration.migrate(db)
        migration.migrate(db)
        assert db.execute("PRAGMA user_version").fetchone()[0] == 4
    after = manifest(path)
    assert all(after[t] == value for t, value in before.items())


def test_failed_migration_rolls_back(tmp_path, monkeypatch):
    db = sqlite3.connect(tmp_path / "test.db")
    db.execute("PRAGMA user_version=3")
    monkeypatch.setattr(migration, "STATEMENTS", (*migration.STATEMENTS, "INVALID SQL"))
    with pytest.raises(sqlite3.Error):
        migration.migrate(db)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 3
    assert (
        db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'research_%'").fetchall() == []
    )
    db.close()


async def test_research_api_requires_opt_in_and_preserves_existing_routes(settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/research/v1/status")).json()[
                "state"
            ] == "schema_not_migrated"
            assert (await client.get("/api/research/v1/experiments")).status_code == 503
            for path in (
                "/health",
                "/api/trades/recent",
                "/api/market/symbols",
                "/api/analytics/candles",
                "/api/analytics/latest",
                "/api/anomalies/recent",
                "/api/anomalies/summary",
                "/api/cross-asset/correlations",
                "/api/cross-asset/matrix",
                "/api/cross-asset/breakdowns",
                "/api/cross-asset/lead-lag",
                "/api/cross-asset/regimes",
                "/api/cross-asset/regimes/latest",
                "/api/cross-asset/status",
            ):
                assert (await client.get(path)).status_code == 200
            assert (await client.get("/api/research/v1/experiments?limit=201")).status_code == 422
            assert (await client.get("/api/research/v1/experiments/not-an-id")).status_code == 422


async def test_populated_research_api_contract(research_source):
    s = research_source
    with sqlite3.connect(s.database_path) as db:
        migration.migrate(db)
    state = run(s, s.database_path)
    app = create_app(s)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            base = f"/api/research/v1/experiments/{state.id}"
            assert (await client.get("/api/research/v1/status")).json()["state"] == "available"
            assert (await client.get(base)).json()["fingerprint"] == state.fingerprint
            for kind in ("metrics", "change-points", "sequences", "discoveries"):
                response = await client.get(base + "/" + kind)
                assert response.status_code == 200 and response.json()
            discovery = (await client.get(base + "/discoveries")).json()[0]
            detail = "/api/research/v1/discoveries/" + discovery["id"]
            assert (await client.get(detail)).json() == discovery
            assert (await client.get(detail + "/evidence")).json()
            assert (await client.get(base + "/metrics?offset=-1")).status_code == 422
            assert (await client.get("/api/research/v1/experiments/" + "0" * 64)).status_code == 404


async def test_atomic_failure_keeps_committed_checkpoint(research_source, tmp_path, monkeypatch):
    import marketpulse.research.worker as worker

    s = research_source
    store = tmp_path / "test.db"
    setup_store(store)
    state = prepare(
        store,
        s.database_path,
        s.analytics.profile_id,
        None,
        START,
        START + timedelta(minutes=99),
        ResearchConfig(),
    )
    state = step(store, state.id, 3)

    def fail(*_):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(worker, "replay", fail)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        step(store, state.id, 3)
    with sqlite3.connect(store) as db:
        value = json.loads(
            db.execute("SELECT experiment_json FROM research_experiments").fetchone()[0]
        )
        assert value["cursor"] == 3 and value["state"] == "failed"
        assert db.execute("SELECT count(*) FROM research_evaluations").fetchone()[0] == 3
