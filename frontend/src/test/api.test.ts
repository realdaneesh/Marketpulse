import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { api, parseResponse } from "../api/client";
import { server } from "./server";
import fixtures from "./fixtures.json";

describe("typed API integration with actual FastAPI-serialized fixtures", () => {
  it("reads all seven contracts without reshaping nullable or decimal values", async () => {
    expect(await api.health()).toEqual(fixtures.ready.health);
    expect(await api.symbols()).toEqual(fixtures.ready.symbols);
    expect(await api.trades()).toEqual(fixtures.ready.trades);
    expect(await api.candles()).toEqual(fixtures.ready.candles);
    expect(await api.latest()).toEqual(fixtures.ready.latest);
    expect(await api.events()).toEqual(fixtures.ready.events);
    expect(await api.summary()).toEqual(fixtures.ready.summary);
  });
  it("sends the exact symbol and bounded limit and keeps response order", async () => {
    server.use(
      http.get("*/api/trades/recent", ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get("symbol")).toBe("ETHUSDT");
        expect(url.searchParams.get("limit")).toBe("10");
        return HttpResponse.json([]);
      }),
    );
    expect(await api.trades("ETHUSDT", 10)).toEqual([]);
    expect(
      (await api.candles("BTCUSDT", 2)).map((c) => c.window_start),
    ).toEqual(fixtures.ready.candles.slice(0, 2).map((c) => c.window_start));
  });
  it("preserves int64 identifiers and decimal strings exactly", () => {
    expect(
      parseResponse(
        '{"trade_id":9223372036854775807,"price":"0.123456789123456789","score":12.5}',
      ),
    ).toEqual({
      trade_id: "9223372036854775807",
      price: "0.123456789123456789",
      score: 12.5,
    });
  });
  it("reports database failure rather than manufacturing an empty result", async () => {
    server.use(
      http.get("*/health", () =>
        HttpResponse.json({ detail: "Database unavailable" }, { status: 503 }),
      ),
    );
    await expect(api.health()).rejects.toMatchObject({ status: 503 });
  });
  it("rejects HTML fallback responses caused by a wrong proxy", async () => {
    server.use(
      http.get("*/api/market/symbols", () =>
        HttpResponse.html("<html>App</html>"),
      ),
    );
    await expect(api.symbols()).rejects.toThrow("Expected JSON");
  });
  it("supports query cancellation", async () => {
    const abort = new AbortController();
    abort.abort();
    await expect(api.trades(undefined, 100, abort.signal)).rejects.toThrow();
  });
});
