import { lazy, Suspense, useMemo } from "react";
import { useCandles, useTrades } from "../api/queries";
import { RangeSelect, SymbolSelect } from "../components/Selectors";
import { useMarketSelection } from "../lib/use-market-selection";
import { TradesTable } from "../components/TradesTable";
import {
  Badge,
  Empty,
  Freshness,
  Metric,
  PageHeading,
  Panel,
  QueryState,
} from "../components/ui";
import { rangeCandles } from "../lib/chart-data";
import { decimal, humanize, number, utc } from "../lib/format";
const MarketChart = lazy(() => import("../components/MarketChart"));

export default function Markets() {
  const selection = useMarketSelection();
  const candles = useCandles(selection.symbol);
  const trades = useTrades(selection.symbol, 100);
  const selected = useMemo(
    () => rangeCandles(candles.data ?? [], selection.range),
    [candles.data, selection.range],
  );
  return (
    <>
      <PageHeading
        eyebrow="MARKET EXPLORER"
        title="Price & participation"
        description="Inspect recorded price action and the trades behind it."
      >
        <SymbolSelect {...selection} onChange={selection.setSymbol} />
      </PageHeading>
      <Panel
        title={`${selection.symbol} / USDT quote`}
        subtitle="Finalized candles · Volume in USDT"
        action={
          <RangeSelect range={selection.range} onChange={selection.setRange} />
        }
      >
        <QueryState query={trades}>
          {(data) => (
            <div className="market-summary">
              <Metric
                label="Latest observed price · USDT"
                value={decimal(data[0]?.price)}
              />
              <div>
                <Freshness timestamp={data[0]?.timestamp} />
                <p className="small-copy muted mt-2">
                  {utc(data[0]?.timestamp)}
                </p>
              </div>
              <Badge>Recorded market data</Badge>
            </div>
          )}
        </QueryState>
        <QueryState query={candles}>
          {() => (
            <>
              <Suspense
                fallback={<div className="loading">Loading chart…</div>}
              >
                <MarketChart
                  key={`${selection.symbol}-${selection.range}`}
                  candles={selected}
                />
              </Suspense>
              <div className="panel-note">
                Range ends at latest fetched candle. {selected.length} of{" "}
                {candles.data?.length} returned windows shown (maximum 1,000).
                No historical pagination or interval resampling.
              </div>
              <div className="chart-legend">
                <span>
                  <i className="legend-green" />
                  Observed up
                </span>
                <span>
                  <i className="legend-red" />
                  Observed down
                </span>
                <span>
                  <i className="legend-amber" />
                  Partial / gap coverage
                </span>
                <span>Missing windows remain blank</span>
              </div>
            </>
          )}
        </QueryState>
      </Panel>
      <Panel
        title="Window detail"
        subtitle="Exact source values for the latest displayed candle"
      >
        <QueryState query={candles}>
          {() => {
            const candle = selected[selected.length - 1];
            return candle ? (
              <>
                <div className="grid gap-5 p-5 sm:grid-cols-2 xl:grid-cols-4">
                  <Metric
                    label="Quote volume · USDT"
                    value={decimal(candle.quote_volume)}
                  />
                  <Metric
                    label="Base volume"
                    value={decimal(candle.base_volume)}
                  />
                  <Metric label="VWAP · USDT" value={decimal(candle.vwap)} />
                  <Metric
                    label="Trade count"
                    value={number(candle.trade_count, 0)}
                  />
                </div>
                <div className="panel-note">
                  {utc(candle.window_start)} → {utc(candle.window_end)} ·{" "}
                  {candle.window_seconds}s · {humanize(candle.quality)}.{" "}
                  {candle.completeness_note}
                </div>
              </>
            ) : (
              <Empty title="No finalized window">
                Window statistics will appear when the analytics worker
                finalizes recorded trades.
              </Empty>
            );
          }}
        </QueryState>
      </Panel>
      <Panel
        title="Recent trades"
        subtitle="Latest 100 committed trades for this market · newest first"
      >
        <QueryState query={trades}>
          {(data) => <TradesTable trades={data} />}
        </QueryState>
      </Panel>
      <p className="footnote">
        Charts use approximate numeric coordinates; readouts and tables retain
        source decimal precision. Aggressor side describes taker direction, not
        a price forecast. Charts by{" "}
        <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">
          TradingView Lightweight Charts™
        </a>
        .
      </p>
    </>
  );
}
