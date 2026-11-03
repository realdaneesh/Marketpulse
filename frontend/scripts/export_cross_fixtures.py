"""Real FastAPI responses over deterministic synthetic, temporary Phase 2/4 data."""

import argparse
import asyncio
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from marketpulse.analytics.config import AnalyticsConfig
from marketpulse.analytics.worker import AnalyticsWorker
from marketpulse.api.app import create_app
from marketpulse.config import Settings
from marketpulse.cross_asset.config import SYMBOLS, CrossAssetConfig
from marketpulse.cross_asset.worker import CrossAssetWorker
from marketpulse.models import Trade

PATHS = {
    "matrix": "matrix",
    "history": "correlations?limit=100",
    "events": "breakdowns",
    "lags": "lead-lag",
    "regimes": "regimes",
    "status": "status",
}


async def capture(path: Path) -> dict:
    settings = Settings(
        _env_file=None,
        database_path=path,
        symbols=SYMBOLS,
        analytics=AnalyticsConfig(min_history=3, history_size=6, allowed_lateness_seconds=0),
        cross_asset=CrossAssetConfig(
            lookback=12,
            min_pairs=6,
            min_coverage=0.75,
            baseline_windows=5,
            min_baseline=3,
            max_lag=2,
            oos_enabled=True,
            oos_min_pairs=3,
        ),
    )
    app = create_app(settings)
    result = {}
    async with app.router.lifespan_context(app):
        repository = app.state.repository
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:

            async def read():
                data = {}
                for key, route in PATHS.items():
                    response = await client.get("/api/cross-asset/" + route)
                    response.raise_for_status()
                    data[key] = response.json()
                # Path is temporary/random; this is configuration metadata, not market evidence.
                data["status"]["database_inside_onedrive"] = False
                return data

            result["empty"] = await read()
            closes = dict.fromkeys(SYMBOLS, 100.0)
            worker = CrossAssetWorker(settings)
            start = datetime(2024, 1, 1, tzinfo=UTC)
            for first, last, name in ((0, 4, "warmup"), (4, 30, "ready"), (30, 44, "breakdown")):
                trades = []
                for minute in range(first, last):
                    for symbol in SYMBOLS:
                        change = (minute % 5 - 2) * 0.002
                        if symbol == "ETHUSDT" and minute >= 30:
                            change = -change
                        closes[symbol] *= math.exp(change)
                        for tick in range(2):
                            trades.append(
                                Trade(
                                    symbol=symbol,
                                    trade_id=minute * 2 + tick + 1,
                                    price=str(closes[symbol]),
                                    quantity="1",
                                    timestamp=start + timedelta(minutes=minute, seconds=tick * 20),
                                    buyer_maker=bool(tick),
                                )
                            )
                await repository.insert_batch(trades)
                await AnalyticsWorker(settings).run_once(repository)
                while (await worker.run_once(repository)).batch_limit_reached:
                    pass
                # Freeze only operational clock metadata inside this disposable test database.
                await repository._run(
                    lambda: repository.connection.execute(
                        "UPDATE cross_profiles SET last_completed_at=?", (start.isoformat(),)
                    )
                )
                await repository._run(repository.connection.commit)
                result[name] = await read()
    return result


parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
with TemporaryDirectory(prefix="marketpulse-cross-test-") as directory:
    data = asyncio.run(capture(Path(directory) / "synthetic.sqlite3"))
destination = Path(__file__).resolve().parents[1] / "src/test/cross-fixtures.json"
content = json.dumps(data, indent=2, sort_keys=True) + "\n"
if args.check:
    if destination.read_text(encoding="utf-8") != content:
        raise SystemExit("Cross-asset fixture contract drift; regenerate fixtures.")
    print("Cross-asset fixtures match actual FastAPI responses.")
else:
    destination.write_text(content, encoding="utf-8")
    print("Exported test-only cross-asset API fixtures; runtime database untouched.")
