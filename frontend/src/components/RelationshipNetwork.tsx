import type { PairStatistic } from "../api/types";
import { assets, coefficient, shortAsset } from "../lib/cross-asset";
import { percent } from "../lib/format";

const positions: Record<string, [number, number]> = {
  BTCUSDT: [200, 48],
  ETHUSDT: [74, 222],
  SOLUSDT: [326, 222],
};
export function RelationshipNetwork({
  pairs,
  onSelect,
}: {
  pairs: PairStatistic[];
  onSelect: (a: string, b: string) => void;
}) {
  const edges = pairs.filter(
    (p) => p.coefficient != null && p.status === "ready",
  );
  return (
    <div className="relationship-network">
      <svg
        viewBox="0 0 400 280"
        role="img"
        aria-label={`Three asset relationship network with ${edges.length} supported correlation edges`}
      >
        {edges.map((p) => {
          const [x1, y1] = positions[p.asset_a];
          const [x2, y2] = positions[p.asset_b];
          const r = p.coefficient!;
          return (
            <g key={`${p.asset_a}-${p.asset_b}`}>
              <line
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={r >= 0 ? "#91cba4" : "#d77d84"}
                strokeDasharray={r < 0 ? "6 5" : undefined}
                strokeWidth={1 + Math.abs(r) * 5}
              >
                <title>{`${shortAsset(p.asset_a)}–${shortAsset(p.asset_b)}: r=${coefficient(r)}, n=${p.sample_count}, coverage=${percent(p.coverage)}`}</title>
              </line>
              <text
                x={(x1 + x2) / 2}
                y={(y1 + y2) / 2 - 10}
                textAnchor="middle"
                fill="#d4e1d8"
                fontSize="12"
              >
                {coefficient(r)}
              </text>
            </g>
          );
        })}
        {assets.map((symbol) => {
          const [cx, cy] = positions[symbol];
          return (
            <g key={symbol}>
              <circle cx={cx} cy={cy} r={28} fill="#202a25" stroke="#53664a" />
              <text
                x={cx}
                y={cy + 4}
                textAnchor="middle"
                fill="#dbe7d5"
                fontSize="12"
              >
                {shortAsset(symbol)}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="small-copy muted">
        Solid green: positive · Dashed red: negative. Width represents |r|.
        Unsupported edges are omitted.
      </p>
      <div className="network-edge-list">
        {pairs.map((p) => (
          <button
            key={`${p.asset_a}-${p.asset_b}`}
            onClick={() => onSelect(p.asset_a, p.asset_b)}
          >
            <span>
              {shortAsset(p.asset_a)}–{shortAsset(p.asset_b)}
            </span>
            <strong>{coefficient(p.coefficient)}</strong>
            <span>
              n={p.sample_count} · {percent(p.coverage)}
            </span>
          </button>
        ))}
      </div>
      <p className="small-copy muted">
        Descriptive relationships among three assets. No causality or contagion
        inference.
      </p>
    </div>
  );
}
