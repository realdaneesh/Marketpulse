import { http, HttpResponse } from "msw";
import fixtures from "./cross-fixtures.json";

export const crossPaths = {
  matrix: "matrix",
  history: "correlations",
  events: "breakdowns",
  lags: "lead-lag",
  regimes: "regimes",
  status: "status",
} as const;
export function crossHandlers(scenario: keyof typeof fixtures = "ready") {
  return Object.entries(crossPaths).map(([key, path]) =>
    http.get(`*/api/cross-asset/${path}`, ({ request }) => {
      const data = fixtures[scenario][key as keyof typeof crossPaths];
      if (key === "lags") {
        const params = new URL(request.url).searchParams;
        const lags = fixtures[scenario].lags;
        return HttpResponse.json({
          ...lags,
          analyses: lags.analyses.filter(
            (a) =>
              (!params.get("leader") || a.leader === params.get("leader")) &&
              (!params.get("follower") ||
                a.follower === params.get("follower")),
          ),
        });
      }
      return HttpResponse.json(data);
    }),
  );
}
