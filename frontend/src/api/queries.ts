import { QueryClient, useQuery } from "@tanstack/react-query";
import { api } from "./client";
import { config } from "../config";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: config.pollMs / 2,
      refetchInterval: config.pollMs,
      refetchIntervalInBackground: false,
      retry: 1,
      refetchOnWindowFocus: true,
    },
  },
});
export const useHealth = () =>
  useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => api.health(signal),
  });
export const useSymbols = () =>
  useQuery({
    queryKey: ["symbols"],
    queryFn: ({ signal }) => api.symbols(signal),
  });
export const useTrades = (symbol?: string, limit = 100) =>
  useQuery({
    queryKey: ["trades", symbol, limit],
    queryFn: ({ signal }) => api.trades(symbol, limit, signal),
  });
export const useCandles = (symbol: string) =>
  useQuery({
    queryKey: ["candles", symbol],
    queryFn: ({ signal }) => api.candles(symbol, 1000, signal),
  });
export const useLatest = (symbol?: string) =>
  useQuery({
    queryKey: ["latest", symbol],
    queryFn: ({ signal }) => api.latest(symbol, signal),
  });
export const useEvents = (symbol?: string) =>
  useQuery({
    queryKey: ["events", symbol],
    queryFn: ({ signal }) => api.events(symbol, 100, signal),
  });
export const useSummary = (symbol?: string) =>
  useQuery({
    queryKey: ["summary", symbol],
    queryFn: ({ signal }) => api.summary(symbol, signal),
  });
