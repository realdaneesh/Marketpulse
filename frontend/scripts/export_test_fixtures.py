"""Capture real API serialization from an isolated, explicitly synthetic test database."""

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from marketpulse.analytics.config import AnalyticsConfig
from marketpulse.analytics.worker import AnalyticsWorker
from marketpulse.api.app import create_app
from marketpulse.config import Settings
from marketpulse.models import Trade

PATHS = {
    "health": "/health",
    "symbols": "/api/market/symbols",
    "trades": "/api/trades/recent",
    "candles": "/api/analytics/candles",
    "latest": "/api/analytics/latest",
    "events": "/api/anomalies/recent",
    "summary": "/api/anomalies/summary",
}


async def capture(path: Path) -> dict:
    settings = Settings(
        _env_file=None,
        database_path=path,
        symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
        analytics=AnalyticsConfig(
            min_history=3,
            history_size=6,
            allowed_lateness_seconds=0,
            min_imbalance_trades=2,
            min_imbalance_quote_volume=1,
        ),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:

            async def read() -> dict:
                result = {}
                for name, endpoint in PATHS.items():
                    response = await client.get(endpoint)
                    response.raise_for_status()
                    result[name] = response.json()
                return result

            empty = await read()
            trades = []
            for minute in range(9):
                prices = ("120", "80", "140", "120") if minute == 6 else ("100",) * 4
                for index, price in enumerate(prices):
                    trades.append(
                        Trade(
                            symbol="BTCUSDT",
                            trade_id=minute * 4 + index + 1,
                            price=price,
                            quantity="1000" if minute == 6 else "1",
                            timestamp=datetime(2024, 1, 1, tzinfo=UTC)
                            + timedelta(minutes=minute, seconds=index * 10),
                            buyer_maker=False if minute == 6 else bool(index % 2),
                        )
                    )
            worker = AnalyticsWorker(settings)
            await app.state.repository.insert_batch(trades[:8])
            await worker.run_once(app.state.repository)
            warmup = await read()
            await app.state.repository.insert_batch(trades[8:])
            await worker.run_once(app.state.repository)
            ready = await read()
            return {"empty": empty, "warmup": warmup, "ready": ready}


parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
with TemporaryDirectory(prefix="marketpulse-frontend-test-") as directory:
    fixtures = asyncio.run(capture(Path(directory) / "synthetic.sqlite3"))
destination = Path(__file__).resolve().parents[1] / "src/test/fixtures.json"
content = json.dumps(fixtures, indent=2, sort_keys=True) + "\n"
if args.check:
    if destination.read_text(encoding="utf-8") != content:
        raise SystemExit("Frontend test fixtures differ from the backend; regenerate them.")
    print("Frontend fixtures match actual backend responses.")
else:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    print("Exported synthetic test-only API responses; no runtime database used.")
