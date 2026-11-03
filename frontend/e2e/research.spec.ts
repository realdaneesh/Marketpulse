import { expect, test } from "@playwright/test";
import fixtures from "../src/test/research-fixtures.json" with { type: "json" };

test("Research Lab reads the isolated synthetic backend and fits the viewport", async ({
  page,
  request,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const status = await request.get("/api/research/v1/status");
  expect(status.status()).toBe(200);
  const data = await status.json();
  expect(data.state).toBe("available");
  expect(data.latest.discrepancies).toBe(0);
  await page.goto("/research");
  await expect(
    page.getByRole("heading", { name: "Research Lab", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Detector evaluation", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Data unavailable")).toHaveCount(0);
  await page.getByRole("button", { name: "Inspect evidence" }).first().click();
  await expect(page.getByText(/Candle ·/)).toBeVisible();
  await page.getByLabel("Evaluation segment").selectOption("test");
  await expect(page.getByText("No eligible segment evaluations")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: `test-results/${info.project.name}-research.png`,
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("Research Lab explains an unmigrated schema without synthetic discoveries", async ({
  page,
}) => {
  await page.route("**/api/research/v1/status", (route) =>
    route.fulfill({ json: fixtures.unmigrated.status }),
  );
  await page.goto("/research");
  await expect(
    page.getByText("Research migration pending approval"),
  ).toBeVisible();
  await expect(page.getByLabel("Historical experiment")).toHaveCount(0);
});
