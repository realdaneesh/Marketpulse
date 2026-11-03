import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { delay, http, HttpResponse } from "msw";
import CrossAsset from "../pages/CrossAsset";
import { crossApi } from "../api/cross-asset";
import { coefficient, correlationSegments } from "../lib/cross-asset";
import type { CorrelationFrame } from "../api/types";
import { renderPage } from "./render";
import { server } from "./server";
import { crossHandlers } from "./cross-server";
import fixtures from "./cross-fixtures.json";

vi.mock("../components/CorrelationChart", () => ({
  default: ({ pair }: { pair: string }) => (
    <div role="img" aria-label={`${pair} test chart`} />
  ),
}));

describe("cross-asset intelligence", () => {
  it("integrates all six read-only client contracts with actual serialized fixtures", async () => {
    expect(await crossApi.matrix()).toEqual(fixtures.ready.matrix);
    expect(await crossApi.history()).toEqual(fixtures.ready.history);
    expect(await crossApi.events()).toEqual(fixtures.ready.events);
    expect(await crossApi.regimes()).toEqual(fixtures.ready.regimes);
    expect(await crossApi.status()).toEqual(fixtures.ready.status);
    const lags = await crossApi.lags("SOLUSDT", "BTCUSDT");
    expect(lags.analyses).toHaveLength(1);
    expect(lags.analyses[0].leader).toBe("SOLUSDT");
  });
  it("shows useful empty states without invented self or off-diagonal coefficients", async () => {
    server.use(...crossHandlers("empty"));
    renderPage(<CrossAsset />);
    expect(
      await screen.findByText("No cross-asset snapshots yet"),
    ).toBeVisible();
    expect(screen.getByText("Regime requires eligible evidence")).toBeVisible();
    expect(screen.getAllByText("Self")).toHaveLength(3);
    expect(screen.queryByText("+1.000")).not.toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /network with 0 supported/ }),
    ).toBeVisible();
  });
  it("retains warm-up, sample counts, and uncertain market regime", async () => {
    server.use(...crossHandlers("warmup"));
    renderPage(<CrossAsset />);
    expect(
      (await screen.findAllByText("Insufficient data")).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("Insufficient history").length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getByText("No supported relationship-change events"),
    ).toBeVisible();
    const cell = screen.getByRole("button", { name: "BTC–ETH correlation" });
    expect(within(cell).getByText("—")).toBeVisible();
  });
  it("matrix selection changes pair history and preserves real signed coefficients", async () => {
    renderPage(<CrossAsset />);
    await screen.findAllByText("High synchronization");
    await userEvent.click(
      screen.getByRole("button", { name: "ETH–SOL correlation" }),
    );
    expect(
      screen.getByRole("heading", { name: "ETH–SOL relationship history" }),
    ).toBeVisible();
    expect(
      screen.getByRole("combobox", { name: "Correlation pair" }),
    ).toHaveValue("ETHUSDT-SOLUSDT");
    expect(
      screen.getByRole("button", { name: "ETH–SOL correlation" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByRole("img", { name: /network with 3 supported/ }),
    ).toBeVisible();
  });
  it("lead–lag selection states the precise direction and holdout limitations", async () => {
    renderPage(<CrossAsset />);
    const row = await screen.findByText("BTC leads ETH by 1 interval (60s)");
    expect(row).toBeVisible();
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Leading asset" }),
      "SOLUSDT",
    );
    expect(
      await screen.findByText("SOL leads ETH by 1 interval (60s)"),
    ).toBeVisible();
    await userEvent.click(screen.getByText("Chronological holdout: Ready"));
    expect(screen.getByText(/not forecast accuracy/)).toBeVisible();
  });
  it("renders backend breakdown explanations and regime evidence", async () => {
    server.use(...crossHandlers("breakdown"));
    renderPage(<CrossAsset />);
    expect(
      (await screen.findAllByText(/Overlapping windows are dependent/)).length,
    ).toBeGreaterThan(0);
    await userEvent.click(screen.getByText("Supporting metrics & thresholds"));
    expect(screen.getByText("Minimum coverage")).toBeVisible();
    expect(screen.getByText("Synchronization")).toBeVisible();
  });
  it("exposes loading and independent API error states", async () => {
    server.use(
      http.get("*/api/cross-asset/matrix", async () => {
        await delay(80);
        return HttpResponse.json({}, { status: 503 });
      }),
    );
    renderPage(<CrossAsset />);
    expect(
      screen.getAllByText("Loading recorded data…").length,
    ).toBeGreaterThan(0);
    expect((await screen.findAllByText("Data unavailable")).length).toBe(3);
  });
  it("retains cached relationships after refresh failure with a warning", async () => {
    const { client } = renderPage(<CrossAsset />);
    await screen.findAllByText("High synchronization");
    server.use(
      http.get("*/api/cross-asset/matrix", () =>
        HttpResponse.json({}, { status: 503 }),
      ),
    );
    await act(() =>
      client.invalidateQueries({ queryKey: ["cross", "matrix"] }),
    );
    expect(
      (await screen.findAllByRole("alert")).some((a) =>
        a.textContent?.includes("Showing cached data"),
      ),
    ).toBe(true);
    expect(
      screen.getByRole("button", { name: "BTC–ETH correlation" }),
    ).toHaveTextContent("+1.000");
  });
  it("formats missing, zero, and negative correlations distinctly", () => {
    expect([null, 0, -0.8, 1].map(coefficient)).toEqual([
      "—",
      "0.000",
      "-0.800",
      "+1.000",
    ]);
  });
  it("splits chart lines at unavailable and compacted intervals", () => {
    const frame = fixtures.ready.history[0] as CorrelationFrame;
    const rows = [0, 1, 2, 4].map((n) => ({
      ...frame,
      window_end: new Date(
        Date.parse(frame.window_end) + n * 60000,
      ).toISOString(),
      skipped_intervals: n === 4 ? 1 : 0,
    }));
    rows[1] = {
      ...rows[1],
      pairs: rows[1].pairs.map((p) => ({
        ...p,
        coefficient: null,
        status: "current_ineligible",
      })),
    };
    expect(correlationSegments(rows, "BTCUSDT-ETHUSDT", 60)).toHaveLength(3);
  });
});
