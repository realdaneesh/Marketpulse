import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import ResearchLab from "../pages/ResearchLab";
import { researchApi } from "../api/research";
import { renderPage } from "./render";
import { server } from "./server";
import fixtures from "./research-fixtures.json";

export function researchHandlers(
  scenario: "unmigrated" | "empty" | "ready" = "ready",
) {
  const data = fixtures[scenario];
  return [
    http.get("*/api/research/v1/status", () => HttpResponse.json(data.status)),
    http.get("*/api/research/v1/experiments", () =>
      HttpResponse.json("experiments" in data ? data.experiments : []),
    ),
    ...["metrics", "change-points", "sequences", "discoveries"].map((kind) =>
      http.get(`*/api/research/v1/experiments/:id/${kind}`, () =>
        HttpResponse.json(kind in data ? data[kind as keyof typeof data] : []),
      ),
    ),
    http.get("*/api/research/v1/discoveries/:id/evidence", () =>
      HttpResponse.json("evidence" in data ? data.evidence : []),
    ),
  ];
}
describe("Research Lab serialized API integration", () => {
  it("keeps small nonzero research effects distinct from zero", async () => {
    server.use(...researchHandlers());
    server.use(
      http.get("*/api/research/v1/experiments/:id/discoveries", () =>
        HttpResponse.json([
          {
            ...fixtures.ready.discoveries[0],
            effect: 0.00007420915723483962,
            baseline: 0.00011374137957910889,
          },
          { ...fixtures.ready.discoveries[1], effect: 0, baseline: null },
        ]),
      ),
    );
    renderPage(<ResearchLab />);
    expect(await screen.findByText("7.421e-5 / 1.137e-4")).toBeVisible();
    expect(screen.getByText("0.000 / Unavailable")).toBeVisible();
  });
  it("integrates the actual temporary backend contracts", async () => {
    server.use(...researchHandlers());
    const id = fixtures.ready.experiments[0].id;
    expect(await researchApi.status()).toEqual(fixtures.ready.status);
    expect(await researchApi.experiments()).toEqual(fixtures.ready.experiments);
    expect(await researchApi.metrics(id)).toEqual(fixtures.ready.metrics);
    expect(await researchApi.changes(id)).toEqual(
      fixtures.ready["change-points"],
    );
    expect(await researchApi.sequences(id)).toEqual(fixtures.ready.sequences);
    expect(await researchApi.discoveries(id)).toEqual(
      fixtures.ready.discoveries,
    );
  });
  it("shows the explicit migration gate without requesting experiments", async () => {
    server.use(...researchHandlers("unmigrated"));
    renderPage(<ResearchLab />);
    expect(
      await screen.findByText("Research migration pending approval"),
    ).toBeVisible();
    expect(
      screen.queryByLabelText("Historical experiment"),
    ).not.toBeInTheDocument();
  });
  it("shows a meaningful empty experiment state", async () => {
    server.use(...researchHandlers("empty"));
    renderPage(<ResearchLab />);
    expect(await screen.findByText("No historical experiments")).toBeVisible();
  });
  it("handles loading then request failure", async () => {
    server.use(
      http.get("*/api/research/v1/status", async () => {
        await delay(150);
        return new HttpResponse(null, { status: 503 });
      }),
    );
    renderPage(<ResearchLab />);
    expect(screen.getByRole("status")).toBeVisible();
    expect(await screen.findByText("Data unavailable")).toBeVisible();
  });
  it("renders research results, evidence, holdout exclusions and sequence insufficiency", async () => {
    const user = userEvent.setup();
    server.use(...researchHandlers());
    renderPage(<ResearchLab />);
    expect(
      await screen.findByRole("heading", { name: "Detector evaluation" }),
    ).toBeVisible();
    expect(screen.getByText(/No independent event labels/)).toBeVisible();
    expect(screen.getAllByText("Insufficient data").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Exploratory").length).toBeGreaterThan(0);
    await user.click(
      screen.getAllByRole("button", { name: "Inspect evidence" })[0],
    );
    expect(await screen.findByText(/Candle ·/)).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Follower"), "BTCUSDT");
    expect(screen.getByText("Choose different assets")).toBeVisible();
    await user.selectOptions(
      screen.getByLabelText("Evaluation segment"),
      "test",
    );
    expect(screen.getByText("No eligible segment evaluations")).toBeVisible();
    expect(
      within(screen.getByLabelText("Historical experiment")).getAllByRole(
        "option",
      ),
    ).toHaveLength(1);
  });
});
