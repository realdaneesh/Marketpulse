import json
import sqlite3

import httpx

from marketpulse.api.app import create_app
from marketpulse.ingestion.parser import parse_trade


async def test_api_health_symbols_recent_and_validation(settings, payload):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json()["ingestion"] == "separate_process_not_monitored"
            assert (await client.get("/api/trades/recent")).json() == []
            await app.state.repository.insert_batch([parse_trade(json.dumps(payload))])
            response = await client.get("/api/trades/recent?symbol=btcusdt&limit=1")
            assert response.status_code == 200
            result = response.json()[0]
            assert result["price"] == payload["p"]
            assert result["quantity"] == payload["q"]
            assert result["timestamp"].endswith("Z")
            assert result["aggressor_side"] == "sell"
            assert (await client.get("/api/market/symbols")).json()["symbols"] == list(
                settings.symbols
            )
            assert (await client.get("/api/trades/recent?limit=0")).status_code == 422
            assert (await client.get("/api/trades/recent?limit=1001")).status_code == 422
            assert (await client.get("/api/trades/recent?symbol=bad%27")).status_code == 422


async def test_health_reports_database_failure(settings, monkeypatch):
    app = create_app(settings)

    async def fail():
        raise sqlite3.OperationalError("unavailable")

    async with app.router.lifespan_context(app):
        monkeypatch.setattr(app.state.repository, "ping", fail)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")
            assert response.status_code == 503
            assert response.json() == {"detail": "Database unavailable"}
