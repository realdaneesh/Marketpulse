import { expect, test } from "@playwright/test";
import fixtures from "../src/test/cross-fixtures.json" with { type: "json" };

test("cross-asset fixture research interactions and API recovery", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const data = fixtures.breakdown;
  const routes: Record<string, unknown> = {
    matrix: data.matrix,
    correlations: data.history,
    breakdowns: data.events,
    "lead-lag": data.lags,
    regimes: data.regimes,
    status: data.status,
  };
  await page.route("**/api/cross-asset/**", (route) => {
    const url = new URL(route.request().url());
    const name = url.pathname.split("/").pop()!;
    if (name === "lead-lag")
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          ...data.lags,
          analyses: data.lags.analyses.filter(
            (a) =>
              a.leader === url.searchParams.get("leader") &&
              a.follower === url.searchParams.get("follower"),
          ),
        }),
      });
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(routes[name]),
    });
  });
  await page.goto("/cross-asset");
  await expect(
    page.getByRole("heading", {
      name: "Cross-Asset Intelligence",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator("canvas").first()).toBeVisible();
  await page
    .getByRole("button", { name: "ETH–SOL correlation", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "ETH–SOL relationship history" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Reset correlation view" }).click();
  await page
    .getByRole("combobox", { name: "Leading asset" })
    .selectOption("SOLUSDT");
  await expect(
    page.getByText("SOL leads ETH by 1 interval (60s)"),
  ).toBeVisible();
  await page.getByText("Supporting metrics & thresholds").click();
  await expect(
    page.getByText("Minimum coverage", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `test-results/${testInfo.project.name}-cross-asset-fixture.png`,
    fullPage: testInfo.project.name === "desktop",
  });
  await page.route("**/api/cross-asset/matrix", (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: "{}" }),
  );
  await page.reload();
  await expect(page.getByText("Data unavailable")).toHaveCount(3, {
    timeout: 20000,
  });
  expect(errors).toEqual([]);
});
