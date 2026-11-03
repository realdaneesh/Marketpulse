function positive(
  value: string | undefined,
  fallback: number,
  minimum: number,
) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= minimum ? parsed : fallback;
}
export const config = {
  apiBase: (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, ""),
  pollMs: positive(import.meta.env.VITE_POLL_INTERVAL_MS, 5000, 1000),
  staleSeconds: positive(import.meta.env.VITE_STALE_AFTER_SECONDS, 60, 1),
};
export const coreSymbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
export const detectorNames = {
  volume: "Volume surge",
  volatility: "Volatility spike",
  imbalance: "Trade imbalance",
  price_shock: "Price shock",
};
