import { useQuery } from "@tanstack/react-query";
import { request } from "./client";
import type {
  BreakdownEvent,
  CorrelationFrame,
  CrossProcessingStatus,
  LeadLagResponse,
  RegimeFrame,
  RelationshipMatrix,
} from "./types";

const root = "/api/cross-asset";
export const crossApi = {
  matrix: (signal?: AbortSignal) =>
    request<RelationshipMatrix>(`${root}/matrix`, signal),
  history: (signal?: AbortSignal) =>
    request<CorrelationFrame[]>(`${root}/correlations?limit=100`, signal),
  events: (signal?: AbortSignal) =>
    request<BreakdownEvent[]>(`${root}/breakdowns?limit=100`, signal),
  lags: (leader: string, follower: string, signal?: AbortSignal) =>
    request<LeadLagResponse>(
      `${root}/lead-lag?${new URLSearchParams({ leader, follower })}`,
      signal,
    ),
  regimes: (signal?: AbortSignal) =>
    request<RegimeFrame[]>(`${root}/regimes?limit=100`, signal),
  status: (signal?: AbortSignal) =>
    request<CrossProcessingStatus>(`${root}/status`, signal),
};
export const useMatrix = () =>
  useQuery({
    queryKey: ["cross", "matrix"],
    queryFn: ({ signal }) => crossApi.matrix(signal),
  });
export const useCorrelationHistory = () =>
  useQuery({
    queryKey: ["cross", "history"],
    queryFn: ({ signal }) => crossApi.history(signal),
  });
export const useBreakdowns = () =>
  useQuery({
    queryKey: ["cross", "events"],
    queryFn: ({ signal }) => crossApi.events(signal),
  });
export const useLeadLag = (leader: string, follower: string) =>
  useQuery({
    queryKey: ["cross", "lags", leader, follower],
    queryFn: ({ signal }) => crossApi.lags(leader, follower, signal),
  });
export const useRegimes = () =>
  useQuery({
    queryKey: ["cross", "regimes"],
    queryFn: ({ signal }) => crossApi.regimes(signal),
  });
export const useCrossStatus = () =>
  useQuery({
    queryKey: ["cross", "status"],
    queryFn: ({ signal }) => crossApi.status(signal),
  });
