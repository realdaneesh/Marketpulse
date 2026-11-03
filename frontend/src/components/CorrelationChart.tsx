import { useEffect, useMemo, useRef } from "react";
import {
  ColorType,
  createChart,
  LineSeries,
  type UTCTimestamp,
} from "lightweight-charts";
import type { CorrelationFrame } from "../api/types";
import { correlationSegments } from "../lib/cross-asset";
import { utc } from "../lib/format";
import { Empty } from "./ui";

export default function CorrelationChart({
  history,
  pair,
  seconds,
}: {
  history: CorrelationFrame[];
  pair: string;
  seconds: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const segments = useMemo(
    () => correlationSegments(history, pair, seconds),
    [history, pair, seconds],
  );
  useEffect(() => {
    if (!host.current || !segments.length) return;
    const chart = createChart(host.current, {
      autoSize: true,
      height: 280,
      layout: {
        background: { type: ColorType.Solid, color: "#15191c" },
        textColor: "#8e999f",
        fontSize: 11,
        attributionLogo: true,
      },
      grid: {
        vertLines: { color: "#20272b" },
        horzLines: { color: "#20272b" },
      },
      timeScale: { timeVisible: true, borderColor: "#2a3135" },
      localization: {
        timeFormatter: (time: number) => utc(time * 1000),
        priceFormatter: (price: number) => price.toFixed(3),
      },
      rightPriceScale: { borderColor: "#2a3135" },
    });
    chartRef.current = chart;
    // Separate series prevent the library drawing a line across excluded intervals.
    for (const segment of segments) {
      const series = chart.addSeries(LineSeries, {
        color: "#b6f279",
        lineWidth: 2,
        pointMarkersVisible: segment.length === 1,
        lastValueVisible: false,
        priceLineVisible: false,
        autoscaleInfoProvider: () => ({
          priceRange: { minValue: -1, maxValue: 1 },
        }),
      });
      series.setData(
        segment.map((p) => ({ ...p, time: p.time as UTCTimestamp })),
      );
    }
    chart.timeScale().fitContent();
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [segments]);
  if (!segments.length)
    return (
      <Empty title="Correlation history needs more eligible returns">
        No supported coefficient is available for this pair. Unavailable
        intervals remain blank.
      </Empty>
    );
  return (
    <div className="chart-wrap">
      <div
        ref={host}
        style={{ height: 280 }}
        role="img"
        aria-label={`${pair} rolling correlation history in UTC`}
      />
      <div className="chart-foot">
        <span>Signed Pearson r · −1 to +1 · gaps are not connected</span>
        <button
          className="text-button"
          onClick={() => chartRef.current?.timeScale().fitContent()}
        >
          Reset correlation view
        </button>
      </div>
    </div>
  );
}
