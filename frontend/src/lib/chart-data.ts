import type { Candle } from "../api/types";
import type { UTCTimestamp } from "lightweight-charts";
import { FinancialDecimal } from "./format";

export type Range = "1H" | "6H" | "24H" | "ALL";
export function rangeCandles(candles: Candle[], range: Range) {
  const sorted = [...candles].sort(
    (a, b) => Date.parse(a.window_start) - Date.parse(b.window_start),
  );
  if (!sorted.length || range === "ALL") return sorted;
  const end = Date.parse(sorted[sorted.length - 1].window_end);
  const start = end - { "1H": 1, "6H": 6, "24H": 24 }[range] * 3600000;
  return sorted.filter((candle) => Date.parse(candle.window_end) > start);
}
export const chartTime = (value: string) =>
  (Date.parse(value) / 1000) as UTCTimestamp;
export function numeric(value: string | number | null | undefined) {
  if (value == null) return null;
  const converted = Number(value);
  return Number.isFinite(converted) &&
    !(converted === 0 && !new FinancialDecimal(value).isZero())
    ? converted
    : null;
}
export function priceData(candles: Candle[]) {
  return candles.map((candle) => {
    const time = chartTime(candle.window_start);
    const [open, high, low, close] = [
      candle.open,
      candle.high,
      candle.low,
      candle.close,
    ].map(numeric);
    if (
      candle.quality === "missing" ||
      open == null ||
      high == null ||
      low == null ||
      close == null
    )
      return { time };
    return {
      time,
      open,
      high,
      low,
      close,
      ...(candle.quality !== "observed"
        ? { color: "#a99058", borderColor: "#a99058", wickColor: "#a99058" }
        : {}),
    };
  });
}
export function volumeData(candles: Candle[]) {
  return candles.map((candle) => {
    const time = chartTime(candle.window_start);
    const value = numeric(candle.quote_volume);
    if (candle.quality === "missing" || value == null) return { time };
    return {
      time,
      value,
      color:
        candle.quality !== "observed"
          ? "#a9905866"
          : (numeric(candle.close) ?? 0) >= (numeric(candle.open) ?? 0)
            ? "#87c99b88"
            : "#d77d8488",
    };
  });
}
