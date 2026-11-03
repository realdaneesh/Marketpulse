import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import App from "../App";
import Overview from "../pages/Overview";
import Intelligence from "../pages/Intelligence";
import Markets from "../pages/Markets";
import System from "../pages/System";
import { RiskScore } from "../components/ui";
import { TradesTable } from "../components/TradesTable";
import type { Risk, Trade } from "../api/types";
import { useTrades } from "../api/queries";
import { handlers, server } from "./server";
import { renderPage } from "./render";
import fixtures from "./fixtures.json";

vi.mock("../components/MarketChart", () => ({
  default: () => <div aria-label="Recorded candle chart" />,
}));

describe("dashboard behavior", () => {
  it("renders real warm-up states and never presents unavailable scores as zero", async () => {
    server.use(...handlers("warmup"));
    renderPage(<Intelligence />);
    expect(await screen.findByText("No matching anomaly events")).toBeVisible();
    expect(await screen.findAllByText("Insufficient history")).not.toHaveLength(
      0,
    );
    expect(
      screen.getAllByText(/required indicators not ready/).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(
      screen.getByText(/not probabilities or investment recommendations/),
    ).toBeVisible();
  });
  it("distinguishes a ready zero score from a null score", () => {
    const risk = fixtures.ready.latest[0].evaluation!.risk as Risk;
    const { rerender } = renderPage(
      <RiskScore
        risk={{ ...risk, score: null, status: "insufficient_history" }}
      />,
    );
    expect(screen.getByText("—")).toBeVisible();
    rerender(<RiskScore risk={{ ...risk, score: 0, status: "ready" }} />);
    expect(screen.getByText("0")).toBeVisible();
    expect(screen.getByText("Ready")).toBeVisible();
  });
  it("shows exact financial text and int64 trade identifiers", () => {
    const trade: Trade = {
      ...fixtures.ready.trades[0],
      exchange: "binance",
      aggressor_side: "sell",
      price: "123456789.123456789123456789",
      trade_id: "9223372036854775807",
    };
    renderPage(<TradesTable trades={[trade]} />);
    expect(screen.getByText("123,456,789.123456789123456789")).toBeVisible();
    expect(screen.getByText("9223372036854775807")).toBeVisible();
    expect(screen.getByText("SELL")).toBeVisible();
  });
  it("keeps collector connectivity unknown even when the API is healthy", async () => {
    renderPage(<System />);
    expect(await screen.findByText("Healthy")).toBeVisible();
    expect(screen.getByText("Unknown")).toBeVisible();
    expect(screen.queryByText(/^Live$/i)).not.toBeInTheDocument();
    expect(screen.getByText("separate_process_not_monitored")).toBeVisible();
  });
  it("provides truthful empty states without chart placeholders or fake prices", async () => {
    server.use(...handlers("empty"));
    renderPage(<Overview />);
    expect(await screen.findByText("No recorded trades")).toBeVisible();
    for (const name of ["Bitcoin", "Ethereum", "Solana"]) {
      const card = screen.getByRole("heading", { name }).closest("article")!;
      expect(within(card).getByText("No observation")).toBeVisible();
    }
    expect(screen.getByText("No matching anomaly events")).toBeVisible();
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
  });
  it("filters alerts by documented severity and expands real contributions", async () => {
    const user = userEvent.setup();
    renderPage(<Intelligence />);
    const summary = await screen.findByText(
      "Detector contributions & event details",
    );
    await user.click(summary);
    expect(
      screen.getByText(`Event: ${fixtures.ready.events[0].id}`),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Low" }));
    expect(screen.getByText("No matching anomaly events")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "High" }));
    expect(screen.getByText("High severity")).toBeVisible();
  });
  it("refetches the selected market and supports range controls", async () => {
    const user = userEvent.setup();
    renderPage(<Markets />);
    const table = await screen.findByRole("table");
    expect(within(table).getAllByText("BTCUSDT").length).toBeGreaterThan(0);
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Market symbol" }),
      "ETHUSDT",
    );
    expect(await screen.findByText("No recorded trades")).toBeVisible();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "1H" }));
    expect(screen.getByRole("button", { name: "1H" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
  it("shows initial API failures and recovers through retry", async () => {
    server.use(
      http.get("*/health", () => HttpResponse.json({}, { status: 503 })),
    );
    renderPage(<System />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Data unavailable",
    );
    server.resetHandlers();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Healthy")).toBeVisible();
  });
  it("retains cached data after refetch failure with a visible warning and unknown health", async () => {
    const { client } = renderPage(<System />);
    expect(await screen.findByText("Healthy")).toBeVisible();
    server.use(
      http.get("*/health", () => HttpResponse.json({}, { status: 503 })),
    );
    await act(() => client.invalidateQueries({ queryKey: ["health"] }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Refresh failed. Showing cached data",
    );
    expect(screen.getByText("Current state unknown")).toBeVisible();
    expect(screen.queryByText("Healthy")).not.toBeInTheDocument();
  });
  it("routes through navigation and restores focus when the mobile menu closes", async () => {
    const user = userEvent.setup();
    renderPage(<App />);
    expect(
      await screen.findByRole("heading", { name: "Market overview" }),
    ).toBeVisible();
    const trigger = screen.getByRole("button", { name: "Open navigation" });
    await user.click(trigger);
    expect(
      screen.getByRole("dialog", { name: "Main navigation" }),
    ).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
    await user.click(screen.getByRole("link", { name: /System Status/ }));
    expect(
      await screen.findByRole("heading", { name: "System status" }),
    ).toBeVisible();
  });
  it("renders a not-found page for unsupported routes", async () => {
    renderPage(<App />, "/unknown");
    expect(
      await screen.findByRole("heading", { name: "Page not found" }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Return to overview" }),
    ).toBeVisible();
  });
  it("polls through TanStack Query and exposes loading before the first response", async () => {
    let calls = 0;
    server.use(
      http.get("*/api/trades/recent", () => {
        calls++;
        return HttpResponse.json(fixtures.ready.trades);
      }),
    );
    function Probe() {
      const query = useTrades("BTCUSDT");
      return (
        <div>
          {query.isPending ? "Loading trades" : `${query.data?.length} trades`}
        </div>
      );
    }
    const { client } = renderPage(<Probe />, "/", 30);
    expect(screen.getByText("Loading trades")).toBeVisible();
    await screen.findByText("36 trades");
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(2));
    client.clear();
  });
});
