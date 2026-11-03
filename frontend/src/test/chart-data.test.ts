import { describe, expect, it } from "vitest";
import type { Candle } from "../api/types";
import {
  numeric,
  priceData,
  rangeCandles,
  volumeData,
} from "../lib/chart-data";
import fixtures from "./fixtures.json";

const candles = fixtures.ready.candles as Candle[];
describe("recorded candle preparation", () => {
  it("omits out-of-range chart numbers instead of plotting false zeroes", () => {
    expect(numeric("1e-999")).toBeNull();
    expect(numeric("1e999")).toBeNull();
    expect(numeric("0")).toBe(0);
  });
  it("sorts newest-first API results chronologically without mutating source data", () => {
    const snapshot = JSON.stringify(candles);
    const result = rangeCandles(candles, "ALL");
    expect(Date.parse(result[0].window_start)).toBeLessThan(
      Date.parse(result[result.length - 1].window_start),
    );
    expect(JSON.stringify(candles)).toBe(snapshot);
  });
  it("anchors time ranges to latest data rather than wall time", () => {
    const old = {
      ...candles[0],
      window_start: "2023-12-31T20:00:00Z",
      window_end: "2023-12-31T20:01:00Z",
    };
    expect(rangeCandles([...candles, old], "1H")).toHaveLength(candles.length);
    expect(rangeCandles([...candles, old], "6H")).toHaveLength(
      candles.length + 1,
    );
  });
  it("represents missing prices and volumes as whitespace, never zero", () => {
    const gap: Candle = {
      ...candles[0],
      quality: "missing",
      open: null,
      high: null,
      low: null,
      close: null,
      quote_volume: null,
      missing_intervals: 8,
    };
    expect(priceData([gap])[0]).not.toHaveProperty("close");
    expect(volumeData([gap])[0]).not.toHaveProperty("value");
  });
  it("marks partial coverage and preserves known zero volume", () => {
    expect(
      priceData([{ ...candles[0], quality: "partial_start" }])[0],
    ).toHaveProperty("color", "#a99058");
    expect(
      volumeData([{ ...candles[0], quote_volume: "0" }])[0],
    ).toHaveProperty("value", 0);
  });
});
