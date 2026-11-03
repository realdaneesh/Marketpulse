import { useSearchParams } from "react-router";
import { useEvents, useLatest, useSummary } from "../api/queries";
import { useMarketSelection } from "../lib/use-market-selection";
import {
  Empty,
  Metric,
  PageHeading,
  Panel,
  QueryState,
} from "../components/ui";
import { number, severity, utc } from "../lib/format";
import { AlertList, EvaluationDetails } from "./intelligence-shared";

export default function Intelligence() {
  const { options } = useMarketSelection();
  const [params, setParams] = useSearchParams();
  const rawSymbol = params.get("symbol") ?? "";
  const symbol = options.includes(rawSymbol) ? rawSymbol : "";
  const rawLevel = params.get("severity") ?? "All";
  const level = ["All", "High", "Elevated", "Low"].includes(rawLevel)
    ? rawLevel
    : "All";
  function update(key: string, value: string) {
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next, { replace: true });
  }
  const events = useEvents(symbol || undefined);
  const summary = useSummary(symbol || undefined);
  const latest = useLatest(symbol || undefined);
  return (
    <>
      <PageHeading
        eyebrow="SIGNAL RESEARCH"
        title="Anomaly intelligence"
        description="Trace unusual activity back to its statistical evidence."
      />
      <div className="notice warning">
        <span>
          Scores are heuristic indicators, not probabilities or investment
          recommendations. Severity bands are display categories: Low &lt;50,
          Elevated 50–&lt;75, High ≥75. Alert thresholds are configured
          separately by the backend.
        </span>
      </div>
      <div className="filter-bar">
        <label className="select-label">
          <span>Market</span>
          <select
            aria-label="Filter alerts by market"
            value={symbol}
            onChange={(event) => update("symbol", event.target.value)}
          >
            <option value="">All markets</option>
            {options.map((option) => (
              <option key={option}>{option}</option>
            ))}
          </select>
        </label>
        <div className="segmented" aria-label="Severity filter">
          {["All", "High", "Elevated", "Low"].map((value) => (
            <button
              key={value}
              aria-pressed={level === value}
              onClick={() => update("severity", value)}
            >
              {value}
            </button>
          ))}
        </div>
        <span className="muted small-copy">
          Severity filters the fetched event sample
        </span>
      </div>
      <Panel
        title="Detection summary"
        subtitle="Symbol-filtered recent sample; severity filter applies only to the event list"
      >
        <QueryState query={summary}>
          {(data) => (
            <div className="grid gap-5 p-5 sm:grid-cols-3">
              <Metric
                label="Events in sample"
                value={number(data.returned_events, 0)}
                hint={`At most ${data.sample_limit} most recent alerts`}
              />
              <Metric
                label="Peak evidence score"
                value={number(data.max_score, 1)}
                hint="Points out of 100"
              />
              <Metric
                label="Latest event end"
                value={
                  <span className="date-value">
                    {utc(data.latest_window_end)}
                  </span>
                }
              />
            </div>
          )}
        </QueryState>
      </Panel>
      <Panel
        title="Detected events"
        subtitle="Select an event’s details to inspect detector contributions"
      >
        <QueryState query={events}>
          {(data) => (
            <AlertList
              events={data.filter(
                (event) =>
                  level === "All" || severity(event.risk.score) === level,
              )}
            />
          )}
        </QueryState>
      </Panel>
      <Panel
        title="Latest detector evaluations"
        subtitle="Current per-market readiness and evidence, independent of event severity filters"
      >
        <QueryState query={latest}>
          {(items) =>
            items.length ? (
              items.map((item) => (
                <EvaluationDetails key={item.symbol} item={item} />
              ))
            ) : (
              <Empty title="No evaluations returned">
                No current evaluation exists for this selection.
              </Empty>
            )
          }
        </QueryState>
      </Panel>
    </>
  );
}
