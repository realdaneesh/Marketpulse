import { useSearchParams } from "react-router";
import { useSymbols } from "../api/queries";
import { coreSymbols } from "../config";
import type { Range } from "./chart-data";

export function useMarketSelection() {
  const [params, setParams] = useSearchParams();
  const symbols = useSymbols();
  const options = [
    ...new Set([...coreSymbols, ...(symbols.data?.symbols ?? [])]),
  ];
  const requested = params.get("symbol") ?? "BTCUSDT";
  const symbol = options.includes(requested) ? requested : "BTCUSDT";
  const rawRange = params.get("range") ?? "6H";
  const range = (
    ["1H", "6H", "24H", "ALL"].includes(rawRange) ? rawRange : "6H"
  ) as Range;
  function update(key: string, value: string) {
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next, { replace: true });
  }
  return {
    symbol,
    range,
    options,
    setSymbol: (value: string) => update("symbol", value),
    setRange: (value: Range) => update("range", value),
  };
}
