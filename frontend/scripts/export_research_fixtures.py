"""Synthetic temporary source -> actual research worker -> serialized FastAPI contracts."""

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
from marketpulse.cross_asset.config import SYMBOLS, CrossAssetConfig
from marketpulse.cross_asset.worker import CrossAssetWorker
from marketpulse.models import Trade
from marketpulse.research.migration import migrate
from marketpulse.research.models import ResearchConfig
from marketpulse.research.worker import prepare, step


def fixture_settings(path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_path=path,
        analytics=AnalyticsConfig(min_history=3, history_size=6, allowed_lateness_seconds=0),
        cross_asset=CrossAssetConfig(
            lookback=12, min_pairs=6, baseline_windows=5, min_baseline=3, max_lag=2
        ),
    )


async def capture(path: Path) -> dict:
    settings = fixture_settings(path)
    app = create_app(settings)
    result = {}
    start = datetime(2024, 1, 1, tzinfo=UTC)
    async with app.router.lifespan_context(app):
        repo = app.state.repository
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            result["unmigrated"] = {"status": (await client.get("/api/research/v1/status")).json()}
            await repo._run(lambda: migrate(repo.connection))

            async def read(state=None):
                values = {
                    "status": (await client.get("/api/research/v1/status")).json(),
                    "experiments": (await client.get("/api/research/v1/experiments")).json(),
                }
                if state:
                    for name in ("metrics", "change-points", "sequences", "discoveries"):
                        response = await client.get(
                            f"/api/research/v1/experiments/{state.id}/{name}?limit=200"
                        )
                        response.raise_for_status()
                        values[name] = response.json()
                    first = values["discoveries"][0]["id"]
                    values["evidence"] = (
                        await client.get(f"/api/research/v1/discoveries/{first}/evidence")
                    ).json()
                return values

            result["empty"] = await read()
            await repo.insert_batch(
                [
                    Trade(
                        symbol=symbol,
                        trade_id=m * 2 + tick + 1,
                        price=str(100 + (m % 7) * 0.3 + tick * 0.01),
                        quantity="100" if m >= 45 else "1",
                        buyer_maker=bool(tick),
                        timestamp=start + timedelta(minutes=m, seconds=tick * 20),
                    )
                    for m in range(100)
                    for symbol in SYMBOLS
                    for tick in range(2)
                ]
            )
            await AnalyticsWorker(settings).run_once(repo)
            while (await CrossAssetWorker(settings).run_once(repo)).batch_limit_reached:
                pass
            state = await asyncio.to_thread(
                prepare,
                path,
                path,
                settings.analytics.profile_id,
                settings.cross_asset.profile_id(settings.analytics.profile_id, 60),
                start,
                start + timedelta(minutes=99),
                ResearchConfig(),
            )
            while state.state not in ("complete", "failed"):
                state = await asyncio.to_thread(step, path, state.id)
            # Freeze operational clocks only, not statistical observations or scores.
            state = state.model_copy(update={"created_at": start, "completed_at": start})
            await repo._run(
                lambda: repo.connection.execute(
                    "UPDATE research_experiments SET experiment_json=? WHERE id=?",
                    (state.model_dump_json(), state.id),
                )
            )
            await repo._run(repo.connection.commit)
            result["ready"] = await read(state)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    with TemporaryDirectory() as directory:
        result = asyncio.run(capture(Path(directory) / "synthetic.sqlite3"))
    target = Path(__file__).resolve().parents[1] / "src/test/research-fixtures.json"
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.check:
        if target.read_text(encoding="utf-8") != text:
            raise SystemExit("Research fixtures differ from actual API serialization")
        print("Research fixtures match actual API serialization")
    else:
        target.write_text(text, encoding="utf-8")
        print("Exported synthetic research contracts")


if __name__ == "__main__":
    main()
