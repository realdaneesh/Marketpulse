import { parse } from "lossless-json";
import { config } from "../config";
import type {
  AnomalyEvent,
  Candle,
  Health,
  LatestAnalytics,
  Summary,
  Symbols,
  Trade,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
// Keep unsafe integer IDs as their original digits, and monetary strings untouched.
export function parseResponse(text: string): unknown {
  return parse(text, undefined, (value) => {
    const number = Number(value);
    return /^-?\d+$/.test(value) && !Number.isSafeInteger(number)
      ? value
      : number;
  });
}
export async function request<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const timeout = AbortSignal.timeout(15000);
  const response = await fetch(`${config.apiBase}${path}`, {
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    headers: { Accept: "application/json" },
  });
  if (!response.ok)
    throw new ApiError(
      response.status,
      `API request failed (${response.status}). Check the API and database.`,
    );
  if (!response.headers.get("content-type")?.includes("application/json")) {
    throw new ApiError(
      response.status,
      "Expected JSON from the API. Check the proxy or API base URL.",
    );
  }
  return parseResponse(await response.text()) as T;
}
function filter(symbol?: string, limit = 100) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (symbol) params.set("symbol", symbol);
  return `?${params}`;
}
export const api = {
  health: (signal?: AbortSignal) => request<Health>("/health", signal),
  symbols: (signal?: AbortSignal) =>
    request<Symbols>("/api/market/symbols", signal),
  trades: (symbol?: string, limit = 100, signal?: AbortSignal) =>
    request<Trade[]>(`/api/trades/recent${filter(symbol, limit)}`, signal),
  candles: (symbol?: string, limit = 1000, signal?: AbortSignal) =>
    request<Candle[]>(`/api/analytics/candles${filter(symbol, limit)}`, signal),
  latest: (symbol?: string, signal?: AbortSignal) =>
    request<LatestAnalytics[]>(
      `/api/analytics/latest${filter(symbol)}`,
      signal,
    ),
  events: (symbol?: string, limit = 100, signal?: AbortSignal) =>
    request<AnomalyEvent[]>(
      `/api/anomalies/recent${filter(symbol, limit)}`,
      signal,
    ),
  summary: (symbol?: string, signal?: AbortSignal) =>
    request<Summary>(`/api/anomalies/summary${filter(symbol)}`, signal),
};
