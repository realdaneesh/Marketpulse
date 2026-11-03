import { expect, test } from "@playwright/test";
import Decimal from "decimal.js";
import fixtures from "../src/test/fixtures.json" with { type: "json" };

// Start the real API + Vite before running this suite. Fixture test is explicit below.
test("all views use actual API responses and fit the viewport", async ({
  page,
  request,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const health = await request.get("/health");
  expect(health.ok()).toBeTruthy();
  expect((await health.json()).ingestion).toBe(
    "separate_process_not_monitored",
  );
  const latestTrade = await (
    await request.get("/api/trades/recent?symbol=BTCUSDT&limit=1")
  ).json();
  const ethCandles = await (
    await request.get("/api/analytics/candles?symbol=ETHUSDT")
  ).json();
  for (const [path, heading] of [
    ["/", "Market overview"],
    ["/markets", "Price & participation"],
    ["/anomalies", "Anomaly intelligence"],
    ["/analytics", "Market analytics"],
    ["/system", "System status"],
    ["/cross-asset", "Cross-Asset Intelligence"],
  ]) {
    await page.goto(path);
    await expect(
      page.getByRole("heading", { name: heading, exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Loading recorded data…")).toHaveCount(0);
    await expect(page.getByText("Data unavailable").first()).not.toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    if (path === "/" && latestTrade.length) {
      const [whole, fraction] = new Decimal(latestTrade[0].price)
        .toFixed()
        .split(".");
      const price =
        whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") +
        (fraction ? `.${fraction}` : "");
      await expect(
        page.locator("article").filter({
          has: page.getByRole("heading", { name: "Bitcoin", exact: true }),
        }),
      ).toContainText(price);
    }
    if (path === "/markets") {
      await page.getByRole("button", { name: "1H", exact: true }).click();
      await expect(
        page.getByRole("button", { name: "1H", exact: true }),
      ).toHaveAttribute("aria-pressed", "true");
      await page
        .getByRole("combobox", { name: "Market symbol" })
        .selectOption("ETHUSDT");
      await expect(
        page.getByRole("heading", { name: "ETHUSDT / USDT quote" }),
      ).toBeVisible();
      if (
        ethCandles.some(
          (candle: { close: string | null }) => candle.close !== null,
        )
      )
        await expect(page.locator("canvas").first()).toBeVisible();
    }
    if (path === "/system")
      await expect(page.getByText("Unknown", { exact: true })).toBeVisible();
    if (path === "/cross-asset")
      await expect(page.getByText("Loading correlation chart…")).toHaveCount(0);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: `test-results/${testInfo.project.name}-${path === "/" ? "overview" : path.slice(1)}.png`,
      fullPage: testInfo.project.name === "desktop",
    });
  }
  expect(errors).toEqual([]);
});

test("synthetic backend fixtures exercise populated charts and event details", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const paths: Record<string, unknown> = {
    "/health": fixtures.ready.health,
    "/api/market/symbols": fixtures.ready.symbols,
    "/api/trades/recent": fixtures.ready.trades,
    "/api/analytics/candles": fixtures.ready.candles,
    "/api/analytics/latest": fixtures.ready.latest,
    "/api/anomalies/recent": fixtures.ready.events,
    "/api/anomalies/summary": fixtures.ready.summary,
  };
  await page.route("**/*", (route) => {
    const path = new URL(route.request().url()).pathname;
    return path in paths
      ? route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(paths[path]),
        })
      : route.continue();
  });
  await page.goto("/markets");
  await expect(page.locator("canvas").first()).toBeVisible();
  await page.getByRole("button", { name: "Reset view" }).click();
  await page.goto("/analytics");
  await expect(page.locator(".chart")).toHaveCount(4);
  await expect(page.locator("canvas").first()).toBeVisible();
  await page.goto("/anomalies");
  await page.getByText("Detector contributions & event details").click();
  await expect(
    page.getByText(`Event: ${fixtures.ready.events[0].id}`),
  ).toBeVisible();
  await page.getByRole("button", { name: "Low", exact: true }).click();
  await expect(page.getByText("No matching anomaly events")).toBeVisible();
  expect(errors).toEqual([]);
});

test("navigation and error recovery work in a real browser", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  if (testInfo.project.name === "mobile") {
    await page.getByRole("button", { name: "Open navigation" }).click();
    await expect(
      page.getByRole("dialog", { name: "Main navigation" }),
    ).toBeVisible();
  }
  await page.getByRole("link", { name: /System Status/ }).click();
  await expect(
    page.getByRole("heading", { name: "System status" }),
  ).toBeVisible();
  await page.route("**/health", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: '{"detail":"Test-only intercepted failure"}',
    }),
  );
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("Data unavailable", {
    timeout: 20000,
  });
  await page.unroute("**/health");
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByText("Healthy", { exact: true })).toBeVisible();
});
