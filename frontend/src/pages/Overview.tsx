import { Activity, ArrowUpRight, Layers3, ScanLine } from "lucide-react";
import { Link } from "react-router";
import { useEvents, useLatest, useSummary, useTrades } from "../api/queries";
import { coreSymbols } from "../config";
import { decimal, humanize, number, utc } from "../lib/format";
import {
  Badge,
  Empty,
  Freshness,
  InlineLink,
  Metric,
  PageHeading,
  Panel,
  QueryState,
  RiskScore,
  Timestamp,
} from "../components/ui";
import { AlertList } from "./intelligence-shared";
import { TradesTable } from "../components/TradesTable";

const assets: Record<
  string,
  { name: string; mark: string; className: string }
> = {
  BTCUSDT: { name: "Bitcoin", mark: "₿", className: "bitcoin" },
  ETHUSDT: { name: "Ethereum", mark: "Ξ", className: "ethereum" },
  SOLUSDT: { name: "Solana", mark: "≋", className: "solana" },
};
function MarketCard({ symbol }: { symbol: string }) {
  const trades = useTrades(symbol, 1);
  const latest = useLatest(symbol);
  const asset = assets[symbol];
  return (
    <article className="market-card">
      <div className="flex items-center justify-between">
        <div className="asset">
          <span className={`asset-icon ${asset.className}`}>{asset.mark}</span>
          <div>
            <h2>{asset.name}</h2>
            <span>{symbol}</span>
          </div>
        </div>
        <Link
          className="icon-button"
          aria-label={`Explore ${symbol}`}
          to={`/markets?symbol=${symbol}`}
        >
          <ArrowUpRight size={19} />
        </Link>
      </div>
      <QueryState query={trades}>
        {(data) => (
          <>
            <div className="market-price">
              {decimal(data[0]?.price)}
              <span>USDT</span>
            </div>
            <div className="price-caption">Latest observed trade</div>
            <Freshness timestamp={data[0]?.timestamp} />
            <div className="market-observed">{utc(data[0]?.timestamp)}</div>
          </>
        )}
      </QueryState>
      <div className="market-stats">
        <QueryState query={latest}>
          {(data) => {
            const candle = data[0]?.evaluation?.candle;
            return (
              <>
                <div>
                  <span>Window volume · USDT</span>
                  <strong>{decimal(candle?.quote_volume)}</strong>
                </div>
                <div>
                  <span>Window trades</span>
                  <strong>
                    {candle ? number(candle.trade_count, 0) : "—"}
                  </strong>
                </div>
                <p>
                  {candle
                    ? `${candle.window_seconds}s finalized window · ${humanize(candle.quality)}`
                    : "Awaiting finalized window"}
                </p>
                {candle && <p>{utc(candle.window_start)}</p>}
              </>
            );
          }}
        </QueryState>
      </div>
    </article>
  );
}
export default function Overview() {
  const latest = useLatest();
  const summary = useSummary();
  const events = useEvents();
  const trades = useTrades(undefined, 8);
  return (
    <>
      <PageHeading
        eyebrow="THE MARKET, IN CONTEXT"
        title="Market overview"
        description="Observed market activity. Explainable signals. A clearer perspective."
      >
        <span className="read-only">
          <ScanLine size={15} />
          Read-only intelligence
        </span>
      </PageHeading>
      <div className="grid gap-4 xl:grid-cols-3">
        {coreSymbols.map((symbol) => (
          <MarketCard key={symbol} symbol={symbol} />
        ))}
      </div>
      <div className="overview-grid">
        <Panel
          title="Intelligence snapshot"
          subtitle="Latest finalized evaluation for each configured market"
          action={<InlineLink to="/anomalies">Explore signals</InlineLink>}
        >
          <QueryState query={latest}>
            {(items) =>
              items.length ? (
                <div className="snapshot-list">
                  {items.map((item) => (
                    <div className="snapshot" key={item.symbol}>
                      <div className="flex items-center justify-between gap-4">
                        <strong>{item.symbol}</strong>
                        <Badge
                          tone={
                            item.status === "ready" ? "positive" : "warning"
                          }
                        >
                          {humanize(item.status)}
                        </Badge>
                      </div>
                      <RiskScore risk={item.evaluation?.risk} />
                      <p>{item.explanation}</p>
                      <div className="snapshot-foot">
                        <span>
                          {item.evaluation?.detectors.filter(
                            (d) => d.status === "ready",
                          ).length ?? 0}{" "}
                          / 4 detectors ready
                        </span>
                        <Freshness timestamp={item.finalized_through} />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty title="No analytics records">
                  The configured markets have no returned evaluations.
                </Empty>
              )
            }
          </QueryState>
          <div className="panel-note">
            <Activity size={15} />
            Scores describe statistical evidence, not future market direction.
          </div>
        </Panel>
        <div className="space-y-4">
          <Panel title="Alert activity" subtitle="Bounded recent-alert sample">
            <QueryState query={summary}>
              {(data) => (
                <>
                  <div className="grid grid-cols-2 gap-4 p-5">
                    <Metric
                      label="Detected events"
                      value={number(data.returned_events, 0)}
                      hint={`Latest ${data.sample_limit} alerts at most`}
                    />
                    <Metric
                      label="Maximum score"
                      value={number(data.max_score, 1)}
                      hint="Heuristic points / 100"
                    />
                  </div>
                  <div className="panel-note">
                    <Layers3 size={15} />
                    {Object.entries(data.by_symbol)
                      .map(([symbol, count]) => `${symbol}: ${count}`)
                      .join(" · ") || "No combined alerts in this sample"}
                  </div>
                </>
              )}
            </QueryState>
          </Panel>
          <Panel
            title="Observation policy"
            subtitle="Know what the data can tell you"
          >
            <div className="policy-content">
              <span className="eyebrow">EVENT TIME, NOT WALL CLOCK</span>
              <p>
                Only finalized windows enter analytics. Gaps and partial
                collection can delay detector readiness.
              </p>
              <div className="policy-rule" />
              <div className="flex items-center justify-between">
                <span>Exchange connection</span>
                <Badge>Unknown</Badge>
              </div>
              <p className="small-copy">
                The collector runs separately. API availability does not
                establish Binance connectivity.
              </p>
              <InlineLink to="/system">Inspect system status</InlineLink>
            </div>
          </Panel>
        </div>
      </div>
      <Panel
        title="Recent anomaly alerts"
        subtitle="Combined signals from the current analytics profile"
        action={<InlineLink to="/anomalies">All recent alerts</InlineLink>}
      >
        <QueryState query={events}>
          {(data) => <AlertList events={data.slice(0, 3)} compact />}
        </QueryState>
      </Panel>
      <Panel
        title="Market tape"
        subtitle="Latest 8 committed trades across all markets"
        action={
          <QueryState query={trades}>
            {(data) => <Timestamp value={data[0]?.timestamp} />}
          </QueryState>
        }
      >
        <QueryState query={trades}>
          {(data) => <TradesTable trades={data} />}
        </QueryState>
      </Panel>
    </>
  );
}
