import { Database, Radio, Server, Workflow } from "lucide-react";
import { useHealth, useLatest, useSymbols, useTrades } from "../api/queries";
import {
  Badge,
  Empty,
  Freshness,
  Metric,
  PageHeading,
  Panel,
  QueryState,
} from "../components/ui";
import { config } from "../config";
import { humanize, number, utc } from "../lib/format";

export default function System() {
  const health = useHealth();
  const trades = useTrades(undefined, 1);
  const latest = useLatest();
  const symbols = useSymbols();
  return (
    <>
      <PageHeading
        eyebrow="OBSERVABILITY"
        title="System status"
        description="Separate service availability from the freshness of market observations."
      />
      <div className="status-grid">
        <Panel title="API & database" action={<Server size={19} />}>
          <QueryState query={health}>
            {(data) => (
              <div className="status-content">
                <div>
                  <span>API response</span>
                  <Badge
                    tone={
                      !health.isError && data.status === "ok"
                        ? "positive"
                        : "warning"
                    }
                  >
                    {health.isError
                      ? "Last check failed"
                      : data.status === "ok"
                        ? "Available"
                        : data.status}
                  </Badge>
                </div>
                <div>
                  <span>Database probe</span>
                  <Badge
                    tone={
                      !health.isError && data.database === "ok"
                        ? "positive"
                        : "warning"
                    }
                  >
                    {health.isError
                      ? "Current state unknown"
                      : data.database === "ok"
                        ? "Healthy"
                        : data.database}
                  </Badge>
                </div>
                <p>
                  Last successful check
                  <br />
                  <span className="mono">{utc(health.dataUpdatedAt)}</span>
                </p>
              </div>
            )}
          </QueryState>
        </Panel>
        <Panel title="Collector connectivity" action={<Radio size={19} />}>
          <div className="status-content">
            <div>
              <span>Binance WebSocket</span>
              <Badge>Unknown</Badge>
            </div>
            <p>
              The API does not monitor the separate collector process. Recent
              trades show observed activity, not a verified current connection.
            </p>
            <code>separate_process_not_monitored</code>
          </div>
        </Panel>
        <Panel title="Last recorded trade" action={<Database size={19} />}>
          <QueryState query={trades}>
            {(data) => (
              <div className="status-content">
                <Freshness timestamp={data[0]?.timestamp} />
                <Metric
                  label={data[0]?.symbol ?? "No recorded market"}
                  value={
                    <span className="date-value">
                      {utc(data[0]?.timestamp)}
                    </span>
                  }
                  hint="Latest committed trade by event timestamp"
                />
              </div>
            )}
          </QueryState>
        </Panel>
      </div>
      <Panel
        title="Analytics progress"
        subtitle="Per-symbol event-time progress in the API’s current policy profile"
        action={<Workflow size={19} />}
      >
        <QueryState query={latest}>
          {(items) =>
            items.length ? (
              <>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Market</th>
                        <th>Readiness</th>
                        <th>Latest processed event (UTC)</th>
                        <th>Finalized through (UTC)</th>
                        <th className="right">Pending</th>
                        <th className="right">Late excluded</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((item) => (
                        <tr key={item.symbol}>
                          <td className="table-symbol">{item.symbol}</td>
                          <td>
                            <Badge
                              tone={
                                item.status === "ready" ? "positive" : "warning"
                              }
                            >
                              {humanize(item.status)}
                            </Badge>
                          </td>
                          <td>
                            <div className="mono small-copy mb-2">
                              {utc(item.max_event_time)}
                            </div>
                            <Freshness timestamp={item.max_event_time} />
                          </td>
                          <td>
                            <div className="mono small-copy mb-2">
                              {utc(item.finalized_through)}
                            </div>
                            <Freshness timestamp={item.finalized_through} />
                          </td>
                          <td className="right mono">
                            {number(item.pending_trades, 0)}
                          </td>
                          <td className="right mono">
                            {number(item.late_trades, 0)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="panel-note">
                  Finalization advances with committed trade event time, not
                  polling or elapsed wall time. The backend does not expose a
                  worker heartbeat; its current process state is unknown.
                </div>
              </>
            ) : (
              <Empty title="No processing records" />
            )
          }
        </QueryState>
      </Panel>
      <Panel
        title="Monitoring configuration"
        subtitle="How this dashboard observes your local services"
      >
        <div className="config-grid">
          <div>
            <span className="label">REST polling</span>
            <strong>Every {config.pollMs / 1000} seconds</strong>
            <p>
              Background tabs pause interval polling. Refocus refreshes stale
              queries.
            </p>
          </div>
          <div>
            <span className="label">Stale observation threshold</span>
            <strong>{config.staleSeconds} seconds</strong>
            <p>
              Age is based on the original event timestamp and your device
              clock.
            </p>
          </div>
          <div>
            <span className="label">Configured subscriptions</span>
            <QueryState query={symbols}>
              {(data) => (
                <>
                  <strong>
                    {data.symbols.join(" · ") || "None configured"}
                  </strong>
                  <p>
                    {data.exchange} public market data · subscriptions do not
                    imply connectivity.
                  </p>
                </>
              )}
            </QueryState>
          </div>
          <div>
            <span className="label">Analytics profile</span>
            <QueryState query={latest}>
              {(items) => (
                <>
                  <strong className="mono small-copy break-all">
                    {[...new Set(items.map((item) => item.profile_id))].join(
                      ", ",
                    ) || "Not available"}
                  </strong>
                  <p>
                    Changing the backend policy selects a separate analytical
                    history.
                  </p>
                </>
              )}
            </QueryState>
          </div>
        </div>
      </Panel>
    </>
  );
}
