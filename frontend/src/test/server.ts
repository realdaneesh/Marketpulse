import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import fixtures from "./fixtures.json";
import { crossHandlers } from "./cross-server";

export const paths = {
  health: "/health",
  symbols: "/api/market/symbols",
  trades: "/api/trades/recent",
  candles: "/api/analytics/candles",
  latest: "/api/analytics/latest",
  events: "/api/anomalies/recent",
  summary: "/api/anomalies/summary",
} as const;
export function handlers(scenario: keyof typeof fixtures = "ready") {
  return Object.entries(paths).map(([key, path]) =>
    http.get(`*${path}`, ({ request }) => {
      const url = new URL(request.url);
      const symbol = url.searchParams.get("symbol");
      const limit = Number(url.searchParams.get("limit") ?? 100);
      const data = fixtures[scenario][key as keyof typeof paths];
      if (Array.isArray(data))
        return HttpResponse.json(
          data
            .filter((item) => !symbol || item.symbol === symbol)
            .slice(0, limit),
        );
      return HttpResponse.json(data);
    }),
  );
}
export const server = setupServer(...handlers(), ...crossHandlers());
