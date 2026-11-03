import type { AnomalyEvent, LatestAnalytics } from "../api/types";
import { detectorNames } from "../config";
import { humanize, number, severity, utc } from "../lib/format";
import { Badge, Contributions, Empty, RiskScore } from "../components/ui";

export function AlertList({
  events,
  compact = false,
}: {
  events: AnomalyEvent[];
  compact?: boolean;
}) {
  if (!events.length)
    return (
      <Empty title="No matching anomaly events">
        No combined alerts were returned for this selection. This can reflect
        insufficient history or no qualifying signals; it does not establish a
        risk-free market.
      </Empty>
    );
  return (
    <div className="alert-list">
      {events.map((event) => (
        <article className="alert-event" key={event.id}>
          <div className="alert-event-heading">
            <span
              className={`event-indicator ${severity(event.risk.score).toLowerCase()}`}
            />
            <div>
              <h3>
                {event.symbol}
                <Badge
                  tone={(event.risk.score ?? 0) >= 75 ? "negative" : "warning"}
                >
                  {severity(event.risk.score)} severity
                </Badge>
              </h3>
              <span className="muted small-copy">
                {utc(event.window_start)} → {utc(event.window_end)}
              </span>
            </div>
            <RiskScore risk={event.risk} />
          </div>
          <p>{event.risk.explanation}</p>
          {!compact && (
            <details>
              <summary>Detector contributions & event details</summary>
              <Contributions risk={event.risk} />
              <div className="detail-meta">
                <span>
                  Alert threshold: {number(event.risk.alert_threshold)} / 100
                </span>
                <span>Event: {event.id}</span>
                <span>Profile: {event.profile_id}</span>
              </div>
            </details>
          )}
        </article>
      ))}
    </div>
  );
}
export function EvaluationDetails({ item }: { item: LatestAnalytics }) {
  const evaluation = item.evaluation;
  return (
    <div className="evaluation">
      <div className="evaluation-heading">
        <div>
          <h3>{item.symbol}</h3>
          <span className="muted small-copy">
            Finalized through {utc(item.finalized_through)}
          </span>
        </div>
        <Badge tone={item.status === "ready" ? "positive" : "warning"}>
          {humanize(item.status)}
        </Badge>
      </div>
      <RiskScore risk={evaluation?.risk} />
      <p>{item.explanation}</p>
      {evaluation ? (
        <>
          <Contributions risk={evaluation.risk} />
          <div className="detector-grid">
            {evaluation.detectors.map((detector) => (
              <div className="detector" key={detector.detector}>
                <div className="flex items-start justify-between gap-3">
                  <h4>{detectorNames[detector.detector]}</h4>
                  <Badge
                    tone={
                      detector.is_anomaly
                        ? "warning"
                        : detector.status === "ready"
                          ? "positive"
                          : "neutral"
                    }
                  >
                    {detector.is_anomaly
                      ? "Signal detected"
                      : humanize(detector.status)}
                  </Badge>
                </div>
                <p>{detector.explanation}</p>
                <dl>
                  <div>
                    <dt>History observations</dt>
                    <dd>{detector.history_count}</dd>
                  </div>
                  <div>
                    <dt>Anomaly score / threshold</dt>
                    <dd>
                      {number(detector.anomaly_score, 4)} /{" "}
                      {number(detector.threshold)}
                    </dd>
                  </div>
                  <div>
                    <dt>Observed metric</dt>
                    <dd>{number(detector.observed_metric, 8)}</dd>
                  </div>
                  <div>
                    <dt>Baseline median</dt>
                    <dd>{number(detector.baseline_metric, 8)}</dd>
                  </div>
                  <div>
                    <dt>Median absolute deviation</dt>
                    <dd>{number(detector.baseline_mad, 8)}</dd>
                  </div>
                  <div>
                    <dt>Effective scale</dt>
                    <dd>{number(detector.effective_scale, 8)}</dd>
                  </div>
                </dl>
              </div>
            ))}
          </div>
          <div className="notice">
            <span>
              Window quality:{" "}
              <strong>{humanize(evaluation.candle.quality)}</strong>.{" "}
              {evaluation.candle.completeness_note}
            </span>
          </div>
        </>
      ) : (
        <Empty title="Waiting for eligible history">
          Keep the collector and analytics worker running. Finalization requires
          new trade event time; polling alone cannot advance the watermark.
        </Empty>
      )}
      <div className="evaluation-foot">
        <span>{number(item.pending_trades, 0)} pending trades</span>
        <span>{number(item.late_trades, 0)} excluded late trades</span>
        <span>Profile {item.profile_id}</span>
      </div>
    </div>
  );
}
