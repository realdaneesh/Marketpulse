import { useQuery } from "@tanstack/react-query";
import { request } from "./client";
import type { components } from "./schema";

type Schemas = components["schemas"];
export type Experiment = Schemas["Experiment"];
export type ResearchMetric = Schemas["Metric"];
export type ResearchChange = Schemas["ChangePoint"];
export type ResearchSequence = Schemas["SequenceResult"];
export type ResearchDiscovery = Schemas["Discovery"];
export type ResearchEvidence = Schemas["Evidence"];
export type ResearchStatus = Schemas["ResearchStatus"];
const base = "/api/research/v1";
export const researchApi = {
  status: (signal?: AbortSignal) =>
    request<ResearchStatus>(`${base}/status`, signal),
  experiments: (signal?: AbortSignal) =>
    request<Experiment[]>(`${base}/experiments?limit=100`, signal),
  metrics: (id: string, signal?: AbortSignal) =>
    request<ResearchMetric[]>(
      `${base}/experiments/${id}/metrics?limit=200`,
      signal,
    ),
  changes: (id: string, signal?: AbortSignal) =>
    request<ResearchChange[]>(
      `${base}/experiments/${id}/change-points?limit=200`,
      signal,
    ),
  sequences: (id: string, signal?: AbortSignal) =>
    request<ResearchSequence[]>(
      `${base}/experiments/${id}/sequences?limit=200`,
      signal,
    ),
  discoveries: (id: string, signal?: AbortSignal) =>
    request<ResearchDiscovery[]>(
      `${base}/experiments/${id}/discoveries?limit=200`,
      signal,
    ),
  evidence: (id: string, signal?: AbortSignal) =>
    request<ResearchEvidence[]>(`${base}/discoveries/${id}/evidence`, signal),
};
export const useResearchStatus = () =>
  useQuery({
    queryKey: ["research", "status"],
    queryFn: ({ signal }) => researchApi.status(signal),
  });
export const useExperiments = (enabled: boolean) =>
  useQuery({
    queryKey: ["research", "experiments"],
    queryFn: ({ signal }) => researchApi.experiments(signal),
    enabled,
  });
export function useResearchResults(id: string | undefined) {
  return useQuery({
    queryKey: ["research", "results", id],
    enabled: Boolean(id),
    queryFn: async ({ signal }) => {
      const [metrics, changes, sequences, discoveries] = await Promise.all([
        researchApi.metrics(id!, signal),
        researchApi.changes(id!, signal),
        researchApi.sequences(id!, signal),
        researchApi.discoveries(id!, signal),
      ]);
      return { metrics, changes, sequences, discoveries };
    },
  });
}
