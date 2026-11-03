import type { Range } from "../lib/chart-data";
export function SymbolSelect({
  symbol,
  options,
  onChange,
}: {
  symbol: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="select-label">
      <span>Market</span>
      <select
        aria-label="Market symbol"
        value={symbol}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((item) => (
          <option key={item}>{item}</option>
        ))}
      </select>
    </label>
  );
}
export function RangeSelect({
  range,
  onChange,
}: {
  range: Range;
  onChange: (value: Range) => void;
}) {
  return (
    <div className="segmented" aria-label="Candle time range">
      {(["1H", "6H", "24H", "ALL"] as const).map((item) => (
        <button
          key={item}
          aria-pressed={range === item}
          onClick={() => onChange(item)}
        >
          {item === "ALL" ? "All fetched" : item}
        </button>
      ))}
    </div>
  );
}
