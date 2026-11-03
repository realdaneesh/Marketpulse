import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
} from "lightweight-charts";
import type { Candle } from "../api/types";
import { chartTime, numeric, priceData, volumeData } from "../lib/chart-data";
import {
  decimal,
  FinancialDecimal,
  humanize,
  percent,
  utc,
} from "../lib/format";
import { Empty } from "./ui";

type Kind =
  | "price"
  | "volume"
  | "realized_volatility"
  | "signed_imbalance"
  | "log_return";
export default function MarketChart({
  candles,
  kind = "price",
}: {
  candles: Candle[];
  kind?: Kind;
}) {
  const host = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const price = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const histogram = useRef<ISeriesApi<"Histogram"> | null>(null);
  const line = useRef<ISeriesApi<"Line"> | null>(null);
  const fitted = useRef(false);
  const candlesRef = useRef(candles);
  const [hovered, setHovered] = useState<Candle | null>(null);
  const hasData = candles.some((c) =>
    kind === "price"
      ? numeric(c.close) != null
      : kind === "volume"
        ? numeric(c.quote_volume) != null
        : numeric(c[kind]) != null,
  );
  useEffect(() => {
    candlesRef.current = candles;
  }, [candles]);

  useEffect(() => {
    if (!host.current || !hasData) return;
    const chart = createChart(host.current, {
      autoSize: true,
      height: kind === "price" ? 370 : 220,
      layout: {
        background: { type: ColorType.Solid, color: "#15191c" },
        textColor: "#8e999f",
        fontFamily: "ui-monospace, monospace",
        fontSize: 11,
        attributionLogo: true,
      },
      grid: {
        vertLines: { color: "#20272b" },
        horzLines: { color: "#20272b" },
      },
      rightPriceScale: { borderColor: "#2a3135" },
      timeScale: {
        borderColor: "#2a3135",
        timeVisible: true,
        secondsVisible: false,
      },
      localization: {
        locale: "en-US",
        timeFormatter: (time: number) => utc(time * 1000),
      },
      crosshair: {
        vertLine: { color: "#69777f" },
        horzLine: { color: "#69777f" },
      },
    });
    chartRef.current = chart;
    if (kind === "price") {
      price.current = chart.addSeries(CandlestickSeries, {
        upColor: "#91cba4",
        downColor: "#d77d84",
        borderVisible: false,
        wickUpColor: "#91cba4",
        wickDownColor: "#d77d84",
      });
      price.current
        .priceScale()
        .applyOptions({ scaleMargins: { top: 0.1, bottom: 0.28 } });
      histogram.current = chart.addSeries(HistogramSeries, {
        priceScaleId: "volume",
        priceFormat: { type: "volume" },
        lastValueVisible: false,
        priceLineVisible: false,
      });
      histogram.current
        .priceScale()
        .applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    } else if (kind === "volume") {
      histogram.current = chart.addSeries(HistogramSeries, {
        priceFormat: { type: "volume" },
        priceLineVisible: false,
      });
    } else {
      line.current = chart.addSeries(LineSeries, {
        color: kind === "signed_imbalance" ? "#b9a5df" : "#b6f279",
        lineWidth: 2,
        pointMarkersVisible: candlesRef.current.length < 3,
        priceLineVisible: false,
        priceFormat: {
          type: "custom",
          formatter: (value: number) => percent(value),
        },
      });
    }
    chart.subscribeCrosshairMove((event) => {
      setHovered(
        candlesRef.current.find(
          (candle) => chartTime(candle.window_start) === event.time,
        ) ?? null,
      );
    });
    return () => {
      chart.remove();
      chartRef.current = null;
      price.current = null;
      histogram.current = null;
      line.current = null;
      fitted.current = false;
    };
  }, [kind, hasData]);
  useEffect(() => {
    if (!chartRef.current) return;
    price.current?.setData(priceData(candles));
    if (price.current) {
      const precision = Math.min(
        12,
        Math.max(
          2,
          ...candles.flatMap((candle) =>
            [candle.open, candle.high, candle.low, candle.close].map((value) =>
              value == null ? 0 : new FinancialDecimal(value).decimalPlaces(),
            ),
          ),
        ),
      );
      price.current.applyOptions({
        priceFormat: { type: "price", precision, minMove: 10 ** -precision },
      });
    }
    histogram.current?.setData(volumeData(candles));
    if (line.current && kind !== "price" && kind !== "volume") {
      line.current.setData(
        candles.map((candle) => {
          const time = chartTime(candle.window_start);
          const value = numeric(candle[kind]);
          return value == null || candle.quality === "missing"
            ? { time }
            : { time, value };
        }),
      );
    }
    if (!fitted.current) {
      chartRef.current.timeScale().fitContent();
      fitted.current = true;
    }
  }, [candles, kind, hasData]);
  if (!hasData)
    return (
      <Empty title="No chartable observations">
        {candles.length
          ? "The returned windows do not contain this metric. Missing values are not zero."
          : "No finalized candles are available in this range. New trade event time is needed to finalize a window."}
      </Empty>
    );
  const selected = hovered ?? candles[candles.length - 1];
  return (
    <div className="chart-wrap">
      <div className="chart-readout">
        <span>{utc(selected.window_start)}</span>
        {kind === "price" ? (
          <>
            <span>
              O <b>{decimal(selected.open)}</b>
            </span>
            <span>
              H <b>{decimal(selected.high)}</b>
            </span>
            <span>
              L <b>{decimal(selected.low)}</b>
            </span>
            <span>
              C <b>{decimal(selected.close)}</b>
            </span>
            <span>
              Vol <b>{decimal(selected.quote_volume)} USDT</b>
            </span>
          </>
        ) : (
          <span>
            {kind === "volume"
              ? `${decimal(selected.quote_volume)} USDT`
              : percent(selected[kind])}
          </span>
        )}
        <span className={selected.quality === "observed" ? "" : "warning-text"}>
          {humanize(selected.quality)}
        </span>
      </div>
      <div
        ref={host}
        className="chart"
        style={{ height: kind === "price" ? 370 : 220 }}
        role="img"
        aria-label={`${kind.replaceAll("_", " ")} chart of recorded ${selected.symbol} candles, UTC`}
      />
      <div className="chart-foot">
        <span>Drag to pan · Scroll to zoom · Crosshair for exact values</span>
        <button
          className="text-button"
          onClick={() => chartRef.current?.timeScale().fitContent()}
        >
          Reset view
        </button>
      </div>
    </div>
  );
}
