import { lazy, Suspense } from "react";
import { useSearchParams } from "react-router";
import {
  useBreakdowns,
  useCorrelationHistory,
  useCrossStatus,
  useLeadLag,
  useMatrix,
  useRegimes,
} from "../api/cross-asset";
import { RelationshipNetwork } from "../components/RelationshipNetwork";
import {
  Badge,
  Empty,
  Freshness,
  Metric,
  PageHeading,
  Panel,
  QueryState,
  Timestamp,
} from "../components/ui";
import {
  assets,
  coefficient,
  findPair,
  pairKey,
  relationships,
  shortAsset,
} from "../lib/cross-asset";
import { humanize, number, percent, utc } from "../lib/format";
const CorrelationChart = lazy(() => import("../components/CorrelationChart"));

export default function CrossAsset() {
  const [params, setParams] = useSearchParams();
  const pair = relationships.includes(params.get("pair") ?? "")
    ? params.get("pair")!
    : relationships[0];
  const [assetA, assetB] = pair.split("-");
  const leader = assets.includes(params.get("leader") ?? "")
    ? params.get("leader")!
    : "BTCUSDT";
  const follower =
    assets.includes(params.get("follower") ?? "") &&
    params.get("follower") !== leader
      ? params.get("follower")!
      : assets.find((a) => a !== leader)!;
  function update(key: string, value: string) {
    const next = new URLSearchParams(params);
    next.set(key, value);
    if (key === "leader") {
      next.set(
        "follower",
        follower === value ? assets.find((a) => a !== value)! : follower,
      );
    }
    setParams(next, { replace: true });
  }
  const matrix = useMatrix(),
    history = useCorrelationHistory(),
    events = useBreakdowns(),
    regimes = useRegimes(),
    status = useCrossStatus(),
    lags = useLeadLag(leader, follower);
  const snapshot = matrix.data?.latest;
  const selected = findPair(snapshot?.pairs ?? [], assetA, assetB);
  return (
    <>
      <PageHeading
        eyebrow="RELATIONSHIP RESEARCH"
        title="Cross-Asset Intelligence"
        description="Explore synchronized movement, changing relationships, and observed market regimes."
      >
        <Freshness timestamp={snapshot?.window_end} />
      </PageHeading>
      <div className="notice">
        <span>
          Only adjacent eligible completed candles enter returns. Correlations
          and selected lags describe association; overlapping windows and lag
          searches create dependence and multiple-testing risk. No causal or
          predictive claims.
        </span>
      </div>
      <Panel
        title="Processing & source readiness"
        subtitle="Publication follows the slowest source’s finalized event-time boundary"
      >
        <QueryState query={status}>
          {(data) => (
            <>
              <div className="cross-processing">
                <Metric
                  label="Cross-asset processing"
                  value={
                    <span className="date-value">{humanize(data.state)}</span>
                  }
                  hint={`Worker heartbeat: ${data.worker_connectivity}`}
                />
                <Metric
                  label="Processed through"
                  value={
                    <span className="date-value">
                      {utc(data.processed_through)}
                    </span>
                  }
                  hint={`${number(data.remaining_intervals, 0)} remaining grid intervals`}
                />
                <Metric
                  label="Source input backlog"
                  value={number(data.source_unstaged_trades, 0)}
                  hint={`${number(data.snapshots, 0)} persisted research snapshots`}
                />
              </div>
              <div className="panel-note">
                {data.explanation}
                {data.database_inside_onedrive &&
                  " Database is inside OneDrive; the README describes verified backup to local storage."}
              </div>
            </>
          )}
        </QueryState>
      </Panel>
      <div className="cross-two-column">
        <Panel
          title="Correlation matrix"
          subtitle="Signed Pearson r · select a relationship to inspect"
        >
          <QueryState query={matrix}>
            {(data) => (
              <>
                <div className="table-scroll">
                  <table className="correlation-matrix">
                    <thead>
                      <tr>
                        <th>Asset</th>
                        {assets.map((a) => (
                          <th key={a}>{shortAsset(a)}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {assets.map((a) => (
                        <tr key={a}>
                          <th scope="row">{shortAsset(a)}</th>
                          {assets.map((b) => {
                            const p = findPair(data.latest?.pairs ?? [], a, b);
                            return (
                              <td key={b}>
                                {a === b ? (
                                  <span
                                    className="muted"
                                    title="Self relationship is not a cross-asset discovery"
                                  >
                                    Self
                                  </span>
                                ) : (
                                  <button
                                    aria-label={`${shortAsset(a)}–${shortAsset(b)} correlation`}
                                    aria-pressed={pair === pairKey(a, b)}
                                    className={`matrix-cell ${p?.coefficient == null ? "unavailable" : p.coefficient >= 0 ? "positive" : "negative"}`}
                                    onClick={() =>
                                      update("pair", pairKey(a, b))
                                    }
                                  >
                                    <strong>
                                      {coefficient(p?.coefficient)}
                                    </strong>
                                    <span>
                                      {p
                                        ? `n=${p.sample_count} · ${percent(p.coverage)}`
                                        : "Awaiting history"}
                                    </span>
                                  </button>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!data.latest && (
                  <Empty title="No cross-asset snapshots yet">
                    Run the cross-asset worker after Phase 2 has finalized
                    source candles. No coefficients are inferred from
                    unsynchronized prices.
                  </Empty>
                )}
                <div className="panel-note">
                  <Timestamp value={data.latest?.window_end} />
                  {data.latest
                    ? `${data.latest.lookback} grid-interval lookback · ${data.latest.window_seconds}s source candles`
                    : data.explanation}
                </div>
              </>
            )}
          </QueryState>
        </Panel>
        <Panel
          title="Relationship network"
          subtitle="Actual coefficients, sample counts, and coverage"
        >
          <QueryState query={matrix}>
            {(data) => (
              <RelationshipNetwork
                pairs={data.latest?.pairs ?? []}
                onSelect={(a, b) => update("pair", pairKey(a, b))}
              />
            )}
          </QueryState>
        </Panel>
      </div>
      <Panel
        title={`${shortAsset(assetA)}–${shortAsset(assetB)} relationship history`}
        subtitle="Latest 100 persisted snapshots · unavailable and compacted intervals break the line"
        action={
          <label className="select-label">
            <span>Relationship</span>
            <select
              aria-label="Correlation pair"
              value={pair}
              onChange={(e) => update("pair", e.target.value)}
            >
              {relationships.map((r) => (
                <option key={r} value={r}>
                  {r.split("-").map(shortAsset).join("–")}
                </option>
              ))}
            </select>
          </label>
        }
      >
        <div className="cross-pair-metrics">
          <Metric
            label="Latest coefficient"
            value={coefficient(selected?.coefficient)}
            hint={
              selected
                ? humanize(selected.status)
                : "Awaiting eligible observations"
            }
          />
          <Metric
            label="Matched observations"
            value={
              selected
                ? `${selected.sample_count} / ${selected.expected_count}`
                : "—"
            }
            hint={
              selected
                ? `${percent(selected.coverage)} grid coverage`
                : undefined
            }
          />
          <Metric
            label="Change from previous interval"
            value={coefficient(selected?.change)}
            hint="Signed coefficient change; unavailable after gaps"
          />
        </div>
        <QueryState query={history}>
          {(data) => (
            <Suspense
              fallback={
                <div className="loading">Loading correlation chart…</div>
              }
            >
              <CorrelationChart
                history={data}
                pair={pair}
                seconds={snapshot?.window_seconds ?? 60}
              />
            </Suspense>
          )}
        </QueryState>
        {snapshot && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Asset</th>
                  <th className="right">Eligible returns</th>
                  <th className="right">Eligible candles</th>
                  <th className="right">Coverage</th>
                  <th className="right">Return volatility</th>
                </tr>
              </thead>
              <tbody>
                {snapshot.assets.map((a) => (
                  <tr key={a.symbol}>
                    <td>{a.symbol}</td>
                    <td className="right mono">
                      {a.eligible_returns}/{a.expected_count}
                    </td>
                    <td className="right mono">
                      {a.eligible_candles}/{a.expected_count}
                    </td>
                    <td className="right mono">{percent(a.coverage)}</td>
                    <td className="right mono">
                      {percent(a.return_volatility)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <Panel
        title="Lead–lag explorer"
        subtitle="A leads B by k intervals: A’s return at t is compared with B’s return at t+k"
      >
        <div className="filter-bar cross-controls">
          <label className="select-label">
            <span>Leading asset A</span>
            <select
              aria-label="Leading asset"
              value={leader}
              onChange={(e) => update("leader", e.target.value)}
            >
              {assets.map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
          </label>
          <label className="select-label">
            <span>Following asset B</span>
            <select
              aria-label="Following asset"
              value={follower}
              onChange={(e) => update("follower", e.target.value)}
            >
              {assets
                .filter((a) => a !== leader)
                .map((a) => (
                  <option key={a}>{a}</option>
                ))}
            </select>
          </label>
        </div>
        <QueryState query={lags}>
          {(data) =>
            data.analyses.length ? (
              data.analyses.map((analysis) => (
                <div key={`${analysis.leader}-${analysis.follower}`}>
                  <p className="cross-copy">{analysis.explanation}</p>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Direction convention</th>
                          <th className="right">Coefficient</th>
                          <th className="right">Samples</th>
                          <th className="right">Coverage</th>
                          <th>Readiness</th>
                        </tr>
                      </thead>
                      <tbody>
                        {analysis.lags.map((lag) => (
                          <tr key={lag.lag}>
                            <td>
                              {shortAsset(analysis.leader)} leads{" "}
                              {shortAsset(analysis.follower)} by {lag.lag}{" "}
                              interval{lag.lag > 1 ? "s" : ""} (
                              {lag.lag * data.window_seconds}s)
                            </td>
                            <td className="right mono">
                              {coefficient(lag.coefficient)}
                            </td>
                            <td className="right mono">
                              {lag.sample_count}/{lag.expected_count}
                            </td>
                            <td className="right mono">
                              {percent(lag.coverage)}
                            </td>
                            <td>
                              <Badge
                                tone={
                                  lag.status === "ready"
                                    ? "positive"
                                    : "neutral"
                                }
                              >
                                {humanize(lag.status)}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="panel-note">
                    Exploratory selected lag:{" "}
                    {analysis.exploratory_selected_lag ?? "unavailable"}.
                    Selection maximizes absolute correlation across supported
                    lags; it is not evidence of predictive skill.
                  </div>
                  <details className="cross-details">
                    <summary>
                      Chronological holdout:{" "}
                      {humanize(analysis.out_of_sample.status)}
                    </summary>
                    <p>{analysis.out_of_sample.explanation}</p>
                    <div className="cross-oos">
                      <span>
                        Split: {utc(analysis.out_of_sample.split_time)}
                      </span>
                      <span>
                        Frozen training lag:{" "}
                        {analysis.out_of_sample.selected_lag ?? "—"}
                      </span>
                      <span>
                        Train r:{" "}
                        {coefficient(analysis.out_of_sample.train_coefficient)}{" "}
                        · n={analysis.out_of_sample.train_count} ·{" "}
                        {percent(analysis.out_of_sample.train_coverage)}
                      </span>
                      <span>
                        Test r:{" "}
                        {coefficient(analysis.out_of_sample.test_coefficient)} ·
                        n={analysis.out_of_sample.test_count} ·{" "}
                        {percent(analysis.out_of_sample.test_coverage)}
                      </span>
                    </div>
                  </details>
                </div>
              ))
            ) : (
              <Empty title="Lead–lag evidence unavailable">
                No completed research snapshot is available for this ordered
                pair. All required target timestamps must already be finalized.
              </Empty>
            )
          }
        </QueryState>
      </Panel>
      <Panel
        title="Observed market regime"
        subtitle="Rule-based characterization with established correlation and volatility baselines"
      >
        <QueryState query={matrix}>
          {(data) =>
            data.latest ? (
              <div className="cross-regime">
                <Badge
                  tone={
                    data.latest.regime.label === "insufficient_data"
                      ? "warning"
                      : "neutral"
                  }
                >
                  {humanize(data.latest.regime.label)}
                </Badge>
                <p>{data.latest.regime.explanation}</p>
                <span className="small-copy muted">
                  Quality: {humanize(data.latest.regime.data_quality)} ·
                  Evidence: {utc(data.latest.regime.evidence_time)}
                </span>
                <details>
                  <summary>Supporting metrics & thresholds</summary>
                  <p>
                    Ready pairs: {data.latest.regime.ready_pairs}/3 · Mean
                    signed correlation:{" "}
                    {coefficient(data.latest.regime.mean_correlation)}
                  </p>
                  <p>
                    Elevated assets:{" "}
                    {data.latest.regime.elevated_assets.join(", ") ||
                      "None supported"}{" "}
                    · Changed relationships:{" "}
                    {data.latest.regime.breakdown_pairs.join(", ") ||
                      "None supported"}
                  </p>
                  <dl>
                    {Object.entries(data.latest.regime.thresholds).map(
                      ([key, value]) => (
                        <div key={key}>
                          <dt>{humanize(key)}</dt>
                          <dd>{number(value, 6)}</dd>
                        </div>
                      ),
                    )}
                  </dl>
                </details>
              </div>
            ) : (
              <Empty title="Regime requires eligible evidence">
                No observed market state has been inferred.
              </Empty>
            )
          }
        </QueryState>
        <QueryState query={regimes}>
          {(data) =>
            data.length ? (
              <div
                className="regime-timeline"
                aria-label="Market regime timeline"
              >
                {data.slice(0, 20).map((frame) => (
                  <details key={frame.regime.evidence_time}>
                    <summary>
                      <time>{utc(frame.regime.evidence_time)}</time>
                      <Badge
                        tone={
                          frame.regime.label === "insufficient_data"
                            ? "warning"
                            : "neutral"
                        }
                      >
                        {humanize(frame.regime.label)}
                      </Badge>
                    </summary>
                    <p>{frame.regime.explanation}</p>
                  </details>
                ))}
              </div>
            ) : (
              <div className="panel-note">No regime history yet.</div>
            )
          }
        </QueryState>
      </Panel>
      <Panel
        title="Correlation breakdown research"
        subtitle="Latest bounded event sample · strengthening/weakening refer to the signed coefficient"
      >
        <QueryState query={events}>
          {(data) =>
            data.length ? (
              data.map((event) => (
                <article className="alert-event" key={event.id}>
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <h3>
                      {shortAsset(event.relationship.asset_a)}–
                      {shortAsset(event.relationship.asset_b)}{" "}
                      <Badge tone="warning">
                        {humanize(event.breakdown.direction)}
                      </Badge>
                    </h3>
                    <Timestamp value={event.window_end} />
                  </div>
                  <p>{event.breakdown.explanation}</p>
                  <div className="cross-event-meta">
                    <span>
                      r={coefficient(event.relationship.coefficient)} · n=
                      {event.relationship.sample_count} · coverage{" "}
                      {percent(event.relationship.coverage)}
                    </span>
                    <span>
                      Deviation {number(event.breakdown.deviation_score, 3)} ·
                      baseline n={event.breakdown.baseline_count}
                    </span>
                  </div>
                </article>
              ))
            ) : (
              <Empty title="No supported relationship-change events">
                Warm-up, coverage, and current eligibility gates suppress
                unsupported discoveries. No events does not imply stable or
                risk-free markets.
              </Empty>
            )
          }
        </QueryState>
        {snapshot && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Current relationship</th>
                  <th>Baseline readiness</th>
                  <th className="right">History windows</th>
                  <th className="right">Median r</th>
                  <th className="right">Deviation</th>
                </tr>
              </thead>
              <tbody>
                {snapshot.breakdowns.map((b) => (
                  <tr key={`${b.asset_a}-${b.asset_b}`}>
                    <td>
                      {shortAsset(b.asset_a)}–{shortAsset(b.asset_b)}
                    </td>
                    <td title={b.explanation}>{humanize(b.status)}</td>
                    <td className="right mono">{b.baseline_count}</td>
                    <td className="right mono">
                      {coefficient(b.baseline_median)}
                    </td>
                    <td className="right mono">
                      {number(b.deviation_score, 3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <p className="footnote">
        Regimes and deviations are descriptive heuristics, not probabilities,
        trading signals, or crash forecasts. Charting by{" "}
        <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">
          TradingView Lightweight Charts™
        </a>
        .
      </p>
    </>
  );
}
