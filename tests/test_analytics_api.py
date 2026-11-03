import httpx
import pytest

from marketpulse.analytics.worker import AnalyticsWorker
from marketpulse.api.app import create_app

PATHS = (
    "/api/analytics/candles",
    "/api/analytics/latest",
    "/api/anomalies/recent",
    "/api/anomalies/summary",
)


async def test_analytics_routes_with_data_and_filters(analytics_settings, make_windows):
    app = create_app(analytics_settings)
    async with app.router.lifespan_context(app):
        await app.state.repository.insert_batch(make_windows())
        await AnalyticsWorker(analytics_settings).run_once(app.state.repository)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            candles = await client.get(PATHS[0] + "?symbol=btcusdt&limit=2")
            assert candles.status_code == 200 and len(candles.json()) == 2
            assert isinstance(candles.json()[0]["quote_volume"], str)
            assert (await client.get(PATHS[0] + "?symbol=ETHUSDT")).json() == []
            latest = (await client.get(PATHS[1] + "?symbol=btcusdt&limit=1")).json()[0]
            assert latest["evaluation"] is not None
            assert len(latest["evaluation"]["detectors"]) == 4
            events = (await client.get(PATHS[2])).json()
            assert len(events) == 1 and events[0]["risk"]["score"] == 100
            summary = (await client.get(PATHS[3] + "?limit=1")).json()
            assert summary["returned_events"] == 1 and summary["sample_limit"] == 1
            assert summary["by_symbol"] == {"BTCUSDT": 1}
            assert (await client.get("/health")).status_code == 200
            assert len((await client.get("/api/trades/recent")).json()) == 36


async def test_empty_database_returns_insufficient_history(settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            latest = (await client.get(PATHS[1])).json()
            assert len(latest) == 3
            assert all(
                item["status"] == "insufficient_history" and item["evaluation"] is None
                for item in latest
            )
            assert (await client.get(PATHS[2])).json() == []


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize(
    "query", ["limit=0", "limit=1001", "limit=abc", "symbol=BTC/USDT", "symbol=x%27"]
)
async def test_api_input_validation(settings, path, query):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            assert (await client.get(f"{path}?{query}")).status_code == 422
