import type { CorrelationFrame, PairStatistic } from "../api/types";

export const assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
export const relationships = [
  "BTCUSDT-ETHUSDT",
  "BTCUSDT-SOLUSDT",
  "ETHUSDT-SOLUSDT",
];
export const shortAsset = (value: string) => value.replace("USDT", "");
export const coefficient = (value: number | null | undefined) =>
  value == null ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(3)}`;
export function findPair(pairs: PairStatistic[], a: string, b: string) {
  return pairs.find(
    (p) =>
      (p.asset_a === a && p.asset_b === b) ||
      (p.asset_a === b && p.asset_b === a),
  );
}
export function pairKey(a: string, b: string) {
  return (
    relationships.find((key) => key.includes(a) && key.includes(b)) ??
    relationships[0]
  );
}
export function correlationSegments(
  history: CorrelationFrame[],
  pair: string,
  seconds: number,
) {
  const [a, b] = pair.split("-");
  const segments: { time: number; value: number }[][] = [];
  let segment: { time: number; value: number }[] = [];
  let previous: number | undefined;
  for (const frame of [...history].sort(
    (x, y) => Date.parse(x.window_end) - Date.parse(y.window_end),
  )) {
    const value = findPair(frame.pairs, a, b)?.coefficient;
    const time = Date.parse(frame.window_end) / 1000;
    if (
      value == null ||
      frame.skipped_intervals > 0 ||
      (previous != null && time - previous !== seconds)
    ) {
      if (segment.length) segments.push(segment);
      segment = [];
    }
    if (value != null) segment.push({ time, value });
    previous = time;
  }
  if (segment.length) segments.push(segment);
  return segments;
}
