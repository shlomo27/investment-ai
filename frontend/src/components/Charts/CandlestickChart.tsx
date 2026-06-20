import React, { useEffect, useRef } from "react";
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  IChartApi,
  IPriceLine,
} from "lightweight-charts";
import { TechnicalAnalysis } from "../../types";

interface Bar { date: string; open: number; high: number; low: number; close: number; volume: number }
interface Point { date: string; value: number }

interface Props {
  ta: TechnicalAnalysis;
  symbol: string;
}

const DARK = {
  bg: "#0f172a",
  surface: "#111827",
  border: "#1f2937",
  text: "#6b7280",
  grid: "#1f293750",
};

function makeChart(el: HTMLDivElement, height: number) {
  return createChart(el, {
    width: el.clientWidth,
    height,
    layout: { background: { color: DARK.surface }, textColor: DARK.text },
    grid: { vertLines: { color: DARK.grid }, horzLines: { color: DARK.grid } },
    crosshair: { mode: 1 },
    rightPriceScale: { borderColor: DARK.border, scaleMargins: { top: 0.1, bottom: 0.05 } },
    timeScale: { borderColor: DARK.border, timeVisible: true, rightOffset: 4 },
  });
}

// ─── Main price chart ────────────────────────────────────────────────────────

const PricePanel: React.FC<{ ta: TechnicalAnalysis; symbol: string }> = ({ ta, symbol }) => {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const bars: Bar[] = (ta as any).price_history ?? [];
    if (!bars.length) return;

    const c = makeChart(ref.current, 340);
    chart.current = c;

    // Candlesticks
    const candles = c.addSeries(CandlestickSeries, {
      upColor: "#22c55e", downColor: "#ef4444",
      borderUpColor: "#22c55e", borderDownColor: "#ef4444",
      wickUpColor: "#22c55e80", wickDownColor: "#ef444480",
    });
    candles.setData(bars.map(b => ({ time: b.date as any, open: b.open, high: b.high, low: b.low, close: b.close })));

    // MA lines
    const maColors: Record<string, string> = { ma20_series: "#60a5fa", ma50_series: "#f59e0b", ma200_series: "#a78bfa" };
    for (const [key, color] of Object.entries(maColors)) {
      const pts: Point[] = (ta as any)[key] ?? [];
      if (pts.length) {
        const s = c.addSeries(LineSeries, { color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        s.setData(pts.map(p => ({ time: p.date as any, value: p.value })));
      }
    }

    // Bollinger Bands (upper + lower as area)
    const bbUpper: Point[] = (ta as any).bb_upper_series ?? [];
    const bbLower: Point[] = (ta as any).bb_lower_series ?? [];
    if (bbUpper.length) {
      const upper = c.addSeries(LineSeries, { color: "#7c3aed30", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      upper.setData(bbUpper.map(p => ({ time: p.date as any, value: p.value })));
    }
    if (bbLower.length) {
      const lower = c.addSeries(LineSeries, { color: "#7c3aed30", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      lower.setData(bbLower.map(p => ({ time: p.date as any, value: p.value })));
    }

    // Support / Resistance horizontal lines
    for (const lvl of (ta.resistance_levels ?? []).slice(0, 3)) {
      candles.createPriceLine({ price: lvl, color: "#ef444460", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "R" });
    }
    for (const lvl of (ta.support_levels ?? []).slice(0, 3)) {
      candles.createPriceLine({ price: lvl, color: "#22c55e60", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "S" });
    }

    // Fibonacci horizontal lines
    const fib = ta.fibonacci_levels;
    if (fib) {
      const fibLevels: [number, string][] = [
        [fib.level_236, "23.6%"], [fib.level_382, "38.2%"],
        [fib.level_500, "50.0%"], [fib.level_618, "61.8%"], [fib.level_786, "78.6%"],
      ];
      for (const [price, label] of fibLevels) {
        if (price) {
          candles.createPriceLine({ price, color: "#f59e0b40", lineWidth: 1, lineStyle: 3, axisLabelVisible: false, title: `Fib ${label}` });
        }
      }
    }

    c.timeScale().fitContent();

    const ro = new ResizeObserver(() => { if (ref.current) c.applyOptions({ width: ref.current.clientWidth }); });
    ro.observe(ref.current);
    return () => { ro.disconnect(); c.remove(); };
  }, [ta]);

  const bars: Bar[] = (ta as any).price_history ?? [];
  if (!bars.length) return (
    <div className="h-[340px] flex items-center justify-center text-gray-700 text-xs tracking-widest">
      NO PRICE DATA — RE-RUN ANALYSIS TO GENERATE CHART
    </div>
  );

  return <div ref={ref} />;
};

// ─── Volume panel ────────────────────────────────────────────────────────────

const VolumePanel: React.FC<{ ta: TechnicalAnalysis }> = ({ ta }) => {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const bars: Bar[] = (ta as any).price_history ?? [];
    if (!bars.length) return;

    const c = createChart(ref.current, {
      width: ref.current.clientWidth,
      height: 80,
      layout: { background: { color: DARK.surface }, textColor: DARK.text },
      grid: { vertLines: { color: DARK.grid }, horzLines: { color: DARK.grid } },
      rightPriceScale: { borderColor: DARK.border, scaleMargins: { top: 0.05, bottom: 0 } },
      timeScale: { borderColor: DARK.border, visible: false },
      crosshair: { mode: 0 },
    });

    const vol = c.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "" });
    vol.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } });
    vol.setData(bars.map(b => ({
      time: b.date as any,
      value: b.volume,
      color: b.close >= b.open ? "#22c55e40" : "#ef444440",
    })));

    c.timeScale().fitContent();
    const ro = new ResizeObserver(() => { if (ref.current) c.applyOptions({ width: ref.current.clientWidth }); });
    ro.observe(ref.current);
    return () => { ro.disconnect(); c.remove(); };
  }, [ta]);

  return <div ref={ref} />;
};

// ─── RSI panel ───────────────────────────────────────────────────────────────

const RSIPanel: React.FC<{ ta: TechnicalAnalysis }> = ({ ta }) => {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const pts: Point[] = (ta as any).rsi_series ?? [];
    if (!pts.length) return;

    const c = createChart(ref.current, {
      width: ref.current.clientWidth,
      height: 100,
      layout: { background: { color: DARK.surface }, textColor: DARK.text },
      grid: { vertLines: { color: DARK.grid }, horzLines: { color: DARK.grid } },
      rightPriceScale: { borderColor: DARK.border, scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { borderColor: DARK.border, visible: false },
      crosshair: { mode: 0 },
    });

    const rsiLine = c.addSeries(LineSeries, { color: "#818cf8", lineWidth: 2, priceLineVisible: false, lastValueVisible: true });
    rsiLine.setData(pts.map(p => ({ time: p.date as any, value: p.value })));
    rsiLine.createPriceLine({ price: 70, color: "#ef444450", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "OB" });
    rsiLine.createPriceLine({ price: 30, color: "#22c55e50", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "OS" });
    rsiLine.applyOptions({ autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }) });

    c.timeScale().fitContent();
    const ro = new ResizeObserver(() => { if (ref.current) c.applyOptions({ width: ref.current.clientWidth }); });
    ro.observe(ref.current);
    return () => { ro.disconnect(); c.remove(); };
  }, [ta]);

  const pts: Point[] = (ta as any).rsi_series ?? [];
  if (!pts.length) return null;
  return <div ref={ref} />;
};

// ─── MACD panel ──────────────────────────────────────────────────────────────

const MACDPanel: React.FC<{ ta: TechnicalAnalysis }> = ({ ta }) => {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const pts: Point[] = (ta as any).macd_series ?? [];
    if (!pts.length) return;

    const c = createChart(ref.current, {
      width: ref.current.clientWidth,
      height: 90,
      layout: { background: { color: DARK.surface }, textColor: DARK.text },
      grid: { vertLines: { color: DARK.grid }, horzLines: { color: DARK.grid } },
      rightPriceScale: { borderColor: DARK.border, scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { borderColor: DARK.border, timeVisible: true, rightOffset: 4 },
      crosshair: { mode: 0 },
    });

    const hist = c.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false });
    hist.setData(pts.map(p => ({
      time: p.date as any,
      value: p.value,
      color: p.value >= 0 ? "#22c55e70" : "#ef444470",
    })));
    hist.createPriceLine({ price: 0, color: "#4b556360", lineWidth: 1, lineStyle: 0, axisLabelVisible: false, title: "" });

    c.timeScale().fitContent();
    const ro = new ResizeObserver(() => { if (ref.current) c.applyOptions({ width: ref.current.clientWidth }); });
    ro.observe(ref.current);
    return () => { ro.disconnect(); c.remove(); };
  }, [ta]);

  const pts: Point[] = (ta as any).macd_series ?? [];
  if (!pts.length) return null;
  return <div ref={ref} />;
};

// ─── Legend ──────────────────────────────────────────────────────────────────

const ChartLegend: React.FC<{ ta: TechnicalAnalysis }> = ({ ta }) => (
  <div className="flex flex-wrap gap-4 px-3 py-2 text-xs font-mono border-b border-gray-800">
    <span className="text-gray-600 flex items-center gap-1.5"><span className="w-3 h-0.5 bg-blue-400 inline-block" />MA20</span>
    <span className="text-gray-600 flex items-center gap-1.5"><span className="w-3 h-0.5 bg-amber-400 inline-block" />MA50</span>
    <span className="text-gray-600 flex items-center gap-1.5"><span className="w-3 h-0.5 bg-violet-400 inline-block" />MA200</span>
    <span className="text-gray-600 flex items-center gap-1.5"><span className="w-3 h-0.5 bg-violet-900 inline-block" />BB Bands</span>
    <span className="text-gray-600 flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-green-700 inline-block" />S</span>
    <span className="text-gray-600 flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-red-700 inline-block" />R</span>
    {ta.fibonacci_levels && <span className="text-gray-600 flex items-center gap-1.5"><span className="w-3 h-0.5 bg-amber-700 inline-block" />Fib</span>}
    {ta.rsi_14 != null && <span className="text-gray-600 ml-auto">RSI {ta.rsi_14.toFixed(1)}</span>}
    {ta.macd_histogram != null && (
      <span className={ta.macd_histogram >= 0 ? "text-green-600" : "text-red-600"}>
        MACD {ta.macd_histogram >= 0 ? "▲" : "▼"}
      </span>
    )}
  </div>
);

// ─── Root export ─────────────────────────────────────────────────────────────

const CandlestickChart: React.FC<Props> = ({ ta, symbol }) => {
  const bars: Bar[] = (ta as any).price_history ?? [];

  return (
    <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-800">
        <p className="text-xs text-gray-500 tracking-widest">
          PRICE CHART · {symbol} · CANDLESTICK {bars.length > 0 ? `(${bars.length} BARS)` : ""}
        </p>
        <div className="flex gap-3 text-xs text-gray-700 font-mono">
          {ta.bb_squeeze && <span className="text-yellow-500 animate-pulse">◈ BB SQUEEZE</span>}
          {ta.macd_crossover && ta.macd_crossover !== "NONE" && (
            <span className={ta.macd_crossover === "BULLISH" ? "text-green-500" : "text-red-500"}>
              MACD {ta.macd_crossover}
            </span>
          )}
        </div>
      </div>

      <ChartLegend ta={ta} />
      <PricePanel ta={ta} symbol={symbol} />

      {bars.length > 0 && (
        <>
          <div className="border-t border-gray-800/50">
            <div className="px-3 py-1 text-xs text-gray-700 tracking-widest">VOLUME</div>
            <VolumePanel ta={ta} />
          </div>
          {(ta as any).rsi_series?.length > 0 && (
            <div className="border-t border-gray-800/50">
              <div className="px-3 py-1 text-xs text-gray-700 tracking-widest">RSI (14)</div>
              <RSIPanel ta={ta} />
            </div>
          )}
          {(ta as any).macd_series?.length > 0 && (
            <div className="border-t border-gray-800/50">
              <div className="px-3 py-1 text-xs text-gray-700 tracking-widest">MACD HISTOGRAM (12·26·9)</div>
              <MACDPanel ta={ta} />
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default CandlestickChart;
