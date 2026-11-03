import type { Trade } from "../api/types";
import { decimal, utc } from "../lib/format";
import { Badge, Empty } from "./ui";

export function TradesTable({ trades }: { trades: Trade[] }) {
  if (!trades.length)
    return (
      <Empty title="No recorded trades">
        Start the collector to observe incoming market activity.
      </Empty>
    );
  return (
    <div className="table-scroll">
      <table>
        <caption className="sr-only">
          Recent committed trades, newest first
        </caption>
        <thead>
          <tr>
            <th>Time (UTC)</th>
            <th>Market</th>
            <th>Aggressor</th>
            <th className="right">Price (USDT)</th>
            <th className="right">Quantity (base)</th>
            <th className="right">Trade ID</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => (
            <tr key={`${trade.exchange}:${trade.symbol}:${trade.trade_id}`}>
              <td className="mono muted">
                {utc(trade.timestamp, true).replace(" UTC", "")}
              </td>
              <td className="table-symbol">{trade.symbol}</td>
              <td>
                <Badge
                  tone={
                    trade.aggressor_side === "buy" ? "positive" : "negative"
                  }
                >
                  {trade.aggressor_side.toUpperCase()}
                </Badge>
              </td>
              <td className="right mono">{decimal(trade.price)}</td>
              <td className="right mono">{decimal(trade.quantity)}</td>
              <td className="right mono muted">{String(trade.trade_id)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
