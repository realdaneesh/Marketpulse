import type { components } from "./schema";

type Schemas = components["schemas"];
// JSON int64 identifiers can exceed JavaScript's safe integer range.
export type Trade = Omit<Schemas["Trade"], "trade_id"> & {
  trade_id: number | string;
};
export type Candle = Omit<
  Schemas["Candle"],
  "first_trade_id" | "last_trade_id"
> & {
  first_trade_id?: number | string | null;
  last_trade_id?: number | string | null;
};
export type LatestAnalytics = Omit<Schemas["LatestAnalytics"], "evaluation"> & {
  evaluation?: { candle: Candle; detectors: Detector[]; risk: Risk } | null;
};
export type Detector = Schemas["DetectorResult"];
export type Risk = Schemas["RiskAssessment"];
export type AnomalyEvent = Schemas["AnomalyEvent"];
export type Summary = Schemas["AnomalySummary"];
export type Health = Schemas["HealthResponse"];
export type Symbols = Schemas["SymbolsResponse"];
export type RelationshipMatrix = Schemas["RelationshipMatrix"];
export type CorrelationFrame = Schemas["CorrelationFrame"];
export type PairStatistic = Schemas["PairStatistic"];
export type CrossSnapshot = Schemas["CrossSnapshot"];
export type BreakdownEvent = Schemas["BreakdownEvent"];
export type LeadLagResponse = Schemas["LeadLagResponse"];
export type RegimeFrame = Schemas["RegimeFrame"];
export type CrossProcessingStatus = Schemas["CrossProcessingStatus"];
