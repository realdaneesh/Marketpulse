import { lazy, Suspense, useMemo } from "react";
import { useCandles, useLatest } from "../api/queries";
import { RangeSelect, SymbolSelect } from "../components/Selectors";
import { useMarketSelection } from "../lib/use-market-selection";
import {
  Empty,
  Freshness,
  Metric,
  PageHeading,
  Panel,
  QueryState,
} from "../components/ui";
import { rangeCandles } from "../lib/chart-data";
import { decimal, FinancialDecimal, number, percent, utc } from "../lib/format";
import { EvaluationDetails } from "./intelligence-shared";
const MarketChart = lazy(() => import("../components/MarketChart"));

export default function Analytics() {
  const selection = useMarketSelection();
  const candles = useCandles(selection.symbol);
  const latest = useLatest(selection.symbol);
  const selected = useMemo(
    () => rangeCandles(candles.data ?? [], selection.range),
    [candles.data, selection.range],
  );
  const recent = selected[selected.length - 1];
  const volumes = selected.filter((c) => c.quote_volume != null);
  const sum = volumes
    .reduce((total, c) => total.plus(c.quote_volume!), new FinancialDecimal(0))
    .toFixed();
  return (
    <>
      <PageHeading
        eyebrow="BEYOND THE PRICE"
        title="Market analytics"
        description="Understand participation, volatility, and directional trade flow."
      >
        <SymbolSelect {...selection} onChange={selection.setSymbol} />
      </PageHeading>
      <div className="filter-bar">
        <RangeSelect range={selection.range} onChange={selection.setRange} />
        <span className="muted small-copy">
          Relative to latest fetched candle · at most 1,000 windows
        </span>
        <Freshness timestamp={recent?.window_end} />
      </div>
      <QueryState query={candles}>
        {() => (
          <>
            <div className="kpi-grid">
              <Metric
                label="Observed quote volume · USDT"
                value={volumes.length ? decimal(sum) : "—"}
                hint={`${volumes.length} windows with volume; excludes unknown values`}
              />
              <Metric
                label="Latest realized volatility"
                value={percent(recent?.realized_volatility)}
                hint="Unannualized · within-window log changes"
              />
              <Metric
                label="Latest signed imbalance"
                value={percent(recent?.signed_imbalance)}
                hint="(Aggressive buy − sell) / base volume"
              />
              <Metric
                label="Latest log return"
                value={percent(recent?.log_return)}
                hint="ln(close / previous eligible close)"
              />
            </div>
            <div className="notice">
              <span>
                Values describe the fetched windows, including marked partial
                coverage. They are not complete exchange totals.{" "}
                {selected.filter((c) => c.quality !== "observed").length}{" "}
                displayed windows have partial, missing, or gap coverage.
              </span>
            </div>
            <div className="analytics-chart-grid">
              {(
                [
                  [
                    "volume",
                    "Trading volume",
                    "Recorded quote notional per finalized window · USDT",
                  ],
                  [
                    "realized_volatility",
                    "Realized volatility",
                    "Square root of summed squared within-window log changes",
                  ],
                  [
                    "signed_imbalance",
                    "Aggressive trade imbalance",
                    "Positive: buy takers · Negative: sell takers · Range −100% to +100%",
                  ],
                  [
                    "log_return",
                    "Price return patterns",
                    "Adjacent eligible candle log returns · gaps remain unavailable",
                  ],
                ] as const
              ).map(([kind, title, subtitle]) => (
                <Panel key={kind} title={title} subtitle={subtitle}>
                  <Suspense
                    fallback={<div className="loading">Loading chart…</div>}
                  >
                    <MarketChart
                      key={`${selection.symbol}-${selection.range}-${kind}`}
                      candles={selected}
                      kind={kind}
                    />
                  </Suspense>
                </Panel>
              ))}
            </div>
            <Panel
              title="Window observations"
              subtitle="Latest 12 displayed windows; exact volumes and descriptive metrics"
            >
              {selected.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Window start (UTC)</th>
                        <th>Coverage</th>
                        <th className="right">Quote volume · USDT</th>
                        <th className="right">Volatility</th>
                        <th className="right">Imbalance</th>
                        <th className="right">Log return</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selected
                        .slice(-12)
                        .reverse()
                        .map((c) => (
                          <tr key={c.window_start}>
                            <td className="mono muted">
                              {utc(c.window_start).replace(" UTC", "")}
                            </td>
                            <td>{c.quality.replaceAll("_", " ")}</td>
                            <td className="mono right">
                              {decimal(c.quote_volume)}
                            </td>
                            <td className="mono right">
                              {percent(c.realized_volatility)}
                            </td>
                            <td className="mono right">
                              {percent(c.signed_imbalance)}
                            </td>
                            <td className="mono right">
                              {percent(c.log_return)}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty title="No finalized observations">
                  The worker needs committed event-time progress to produce
                  analytical windows.
                </Empty>
              )}
            </Panel>
          </>
        )}
      </QueryState>
      <Panel
        title="Detector statistics"
        subtitle="Latest evaluation only; historical detector frequencies are not exposed by the API"
      >
        <QueryState query={latest}>
          {(items) =>
            items.length ? (
              items.map((item) => (
                <div key={item.symbol}>
                  <div className="panel-note">
                    {number(
                      item.evaluation?.detectors.filter((d) => d.is_anomaly)
                        .length ?? 0,
                    )}{" "}
                    current detector flags ·{" "}
                    {number(
                      item.evaluation?.detectors.filter(
                        (d) => d.status === "ready",
                      ).length ?? 0,
                    )}{" "}
                    ready detectors
                  </div>
                  <EvaluationDetails item={item} />
                </div>
              ))
            ) : (
              <Empty title="No detector statistics" />
            )
          }
        </QueryState>
      </Panel>
      <p className="footnote">
        No unavailable metric is imputed. Chart coordinates are approximate;
        exact monetary values are available in the tables.{" "}
        <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">
          TradingView Lightweight Charts™
        </a>
        .
      </p>
    </>
  );
}
