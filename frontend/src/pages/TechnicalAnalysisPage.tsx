import React, { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell,
} from "recharts";
import { useAppSelector } from "../store";
import { recommendationsApi, ordersApi } from "../api/client";
import {
  Recommendation, RecommendationType, TechnicalAnalysis,
  OrderType, AnalysisModule, FibonacciLevels,
} from "../types";
import ConfirmTradeModal from "../components/Trading/ConfirmTradeModal";

// ─── Signal colours ─────────────────────────────────────────────────────────

const SIG: Record<string, { bar: string; text: string; bg: string; border: string }> = {
  STRONG_BUY:  { bar: "bg-green-500",  text: "text-green-300",  bg: "bg-green-900/20",  border: "border-green-700/40" },
  BUY_NOW:     { bar: "bg-green-600",  text: "text-green-400",  bg: "bg-green-950/30",  border: "border-green-800/30" },
  WAIT:        { bar: "bg-yellow-500", text: "text-yellow-300", bg: "bg-yellow-900/10", border: "border-yellow-800/30" },
  SELL_NOW:    { bar: "bg-red-600",    text: "text-red-400",    bg: "bg-red-950/30",    border: "border-red-800/30" },
  STRONG_SELL: { bar: "bg-red-500",    text: "text-red-300",    bg: "bg-red-900/20",    border: "border-red-700/40" },
};

const MOD_SIGNAL: Record<string, { dot: string; text: string; badge: string }> = {
  BULLISH: { dot: "bg-green-500", text: "text-green-300", badge: "bg-green-900/40 text-green-400 border-green-700/40" },
  BEARISH: { dot: "bg-red-500",   text: "text-red-300",   badge: "bg-red-900/40 text-red-400 border-red-700/40" },
  NEUTRAL: { dot: "bg-gray-500",  text: "text-gray-400",  badge: "bg-gray-800 text-gray-400 border-gray-700" },
};

const CAT_ICON: Record<string, string> = {
  TREND: "↗", MOMENTUM: "⚡", VOLATILITY: "◈", VOLUME: "▮", PATTERN: "⬡", STRUCTURE: "⊞",
};

const WYCKOFF_LABEL: Record<string, { label: string; color: string; desc: string }> = {
  ACCUMULATION: { label: "ACCUMULATION", color: "text-blue-400 border-blue-700/40 bg-blue-900/20", desc: "Smart money building positions — potential markup ahead" },
  MARKUP:       { label: "MARKUP",       color: "text-green-400 border-green-700/40 bg-green-900/20", desc: "Uptrend phase — trend followers entering" },
  DISTRIBUTION: { label: "DISTRIBUTION", color: "text-orange-400 border-orange-700/40 bg-orange-900/20", desc: "Smart money distributing — potential markdown ahead" },
  MARKDOWN:     { label: "MARKDOWN",     color: "text-red-400 border-red-700/40 bg-red-900/20", desc: "Downtrend phase — selling pressure dominant" },
  UNKNOWN:      { label: "UNKNOWN",      color: "text-gray-500 border-gray-700 bg-gray-800/40", desc: "Phase not determinable from available data" },
};

// ─── 52-Week range bar ───────────────────────────────────────────────────────

const RangeBar: React.FC<{ ta: TechnicalAnalysis }> = ({ ta }) => {
  const low52  = ta.week52_low  ?? ta.support_levels?.[0];
  const high52 = ta.week52_high ?? ta.resistance_levels?.[0];
  const current = ta.current_price;
  if (!low52 || !high52 || high52 <= low52 || !current) return (
    <p className="text-xs text-gray-700 text-center py-4">No range data available</p>
  );

  const pct = (v: number) => Math.min(Math.max(((v - low52) / (high52 - low52)) * 100, 0), 100);
  const curPct  = pct(current);
  const ma50Pct  = ta.ma_50  ? pct(ta.ma_50)  : null;
  const ma200Pct = ta.ma_200 ? pct(ta.ma_200) : null;

  return (
    <div className="space-y-3">
      <div className="flex justify-between text-xs text-gray-600 font-mono">
        <span>52W LOW  ${low52.toFixed(2)}</span>
        <span className="text-gray-500">52-WEEK RANGE</span>
        <span>52W HIGH ${high52.toFixed(2)}</span>
      </div>
      <div className="relative h-5 bg-gray-800 rounded-full overflow-visible">
        <div className="absolute inset-0 rounded-full bg-gradient-to-r from-red-800/60 via-yellow-800/30 to-green-800/60" />
        {ma200Pct != null && (
          <div className="absolute top-0 w-0.5 h-5 bg-orange-500/80 z-10" style={{ left: `${ma200Pct}%` }} title={`MA200 $${ta.ma_200?.toFixed(2)}`} />
        )}
        {ma50Pct != null && (
          <div className="absolute top-0 w-0.5 h-5 bg-blue-400/80 z-10" style={{ left: `${ma50Pct}%` }} title={`MA50 $${ta.ma_50?.toFixed(2)}`} />
        )}
        <div
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-4 h-4 bg-white rounded-full shadow-lg shadow-white/40 z-20 border-2 border-gray-900"
          style={{ left: `${curPct}%` }}
        />
      </div>
      <div className="flex justify-between text-xs font-mono">
        {ma200Pct != null ? <span className="text-orange-400/70">MA200 ${ta.ma_200?.toFixed(0)}</span> : <span />}
        <span className="text-white font-bold">${current.toFixed(2)}</span>
        {ma50Pct != null ? <span className="text-blue-400/70">MA50 ${ta.ma_50?.toFixed(0)}</span> : <span />}
      </div>
    </div>
  );
};

// ─── Fibonacci levels ────────────────────────────────────────────────────────

const FibPanel: React.FC<{ fib: FibonacciLevels; current: number }> = ({ fib, current }) => {
  const levels: { key: keyof FibonacciLevels; label: string; color: string }[] = [
    { key: "level_786", label: "78.6%", color: "text-purple-400" },
    { key: "level_618", label: "61.8%", color: "text-blue-400" },
    { key: "level_500", label: "50.0%", color: "text-cyan-400" },
    { key: "level_382", label: "38.2%", color: "text-green-400" },
    { key: "level_236", label: "23.6%", color: "text-yellow-400" },
  ];
  const isNear = (v: number) => Math.abs((current - v) / current) < 0.015;

  return (
    <div className="space-y-1">
      <div className="text-xs text-gray-700 font-mono mb-2">
        HIGH ${fib.swing_high.toFixed(2)} · LOW ${fib.swing_low.toFixed(2)}
      </div>
      {levels.map(l => {
        const val = fib[l.key] as number;
        if (!val) return null;
        const near = isNear(val);
        return (
          <div key={l.key} className={`flex items-center gap-3 text-xs font-mono px-3 py-1.5 rounded ${near ? "bg-yellow-900/30 border border-yellow-700/40" : ""}`}>
            <span className={`${l.color} w-12`}>{l.label}</span>
            <span className="text-gray-300 font-bold">${val.toFixed(2)}</span>
            <span className="text-gray-600 ml-auto">{((val - current) / current * 100).toFixed(1)}%</span>
            {near && <span className="text-yellow-400 text-xs">← HERE</span>}
          </div>
        );
      })}
    </div>
  );
};

// ─── Score breakdown chart ────────────────────────────────────────────────────

const BreakdownChart: React.FC<{ items: AnalysisModule[] }> = ({ items }) => {
  const data = items.map(m => ({
    name: m.name.length > 16 ? m.name.slice(0, 15) + "…" : m.name,
    score: m.score_impact,
    bull: m.signal === "BULLISH",
    neutral: m.signal === "NEUTRAL",
  }));

  return (
    <ResponsiveContainer width="100%" height={items.length * 34 + 20}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 36, left: 0, bottom: 0 }} barSize={12}>
        <XAxis type="number" domain={[-26, 26]} hide />
        <YAxis type="category" dataKey="name" width={130} tick={{ fill: "#6b7280", fontSize: 10, fontFamily: "monospace" }} />
        <ReferenceLine x={0} stroke="#374151" strokeWidth={1} />
        <Tooltip
          cursor={{ fill: "#1f293720" }}
          contentStyle={{ background: "#0f172a", border: "1px solid #374151", borderRadius: 8, fontSize: 11, fontFamily: "monospace" }}
          formatter={(v: number) => [`${v > 0 ? "+" : ""}${v}`, "score impact"]}
        />
        <Bar dataKey="score" radius={[0, 4, 4, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.bull ? "#22c55e" : d.neutral ? "#eab308" : "#ef4444"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
};

// ─── Analysis module row ──────────────────────────────────────────────────────

const ModuleCard: React.FC<{ mod: AnalysisModule }> = ({ mod }) => {
  const s = MOD_SIGNAL[mod.signal] ?? MOD_SIGNAL.NEUTRAL;
  const icon = CAT_ICON[mod.category] ?? "·";
  return (
    <div className="flex items-start gap-3 px-4 py-3 border-b border-gray-800/50 last:border-0">
      <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${s.dot}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-gray-600 text-xs">{icon}</span>
          <span className="text-xs font-bold text-gray-300 tracking-wide">{mod.name.toUpperCase()}</span>
          <span className={`ml-auto text-xs px-1.5 py-0.5 rounded border font-bold flex-shrink-0 ${s.badge}`}>
            {mod.signal}
          </span>
        </div>
        <p className="text-xs text-gray-500 leading-relaxed">{mod.detail}</p>
      </div>
      <div className={`text-xs font-bold flex-shrink-0 w-10 text-right ${
        mod.score_impact > 0 ? "text-green-400" : mod.score_impact < 0 ? "text-red-400" : "text-gray-600"
      }`}>
        {mod.score_impact > 0 ? "+" : ""}{mod.score_impact}
      </div>
    </div>
  );
};

// ─── Price levels ────────────────────────────────────────────────────────────

const PriceLevels: React.FC<{ ta: TechnicalAnalysis }> = ({ ta }) => {
  const current = ta.current_price;
  if (!current) return null;
  const supports = (ta.support_levels ?? []).slice(0, 3);
  const resistances = (ta.resistance_levels ?? []).slice(0, 3);
  if (!supports.length && !resistances.length) return null;

  return (
    <div className="space-y-1 font-mono">
      {resistances.map(r => (
        <div key={r} className="flex items-center gap-3 text-xs">
          <span className="text-red-400 font-bold w-20">${r.toFixed(2)}</span>
          <div className="flex-1 h-1 bg-gray-800 rounded-full">
            <div className="h-1 bg-red-700/60 rounded-full" style={{ width: `${Math.min(Math.abs(r - current) / current * 200 + 30, 92)}%` }} />
          </div>
          <span className="text-red-600 w-16 text-right">+{((r - current) / current * 100).toFixed(1)}% R</span>
        </div>
      ))}
      <div className="flex items-center gap-3 text-xs py-0.5">
        <span className="text-white font-bold w-20">${current.toFixed(2)}</span>
        <div className="flex-1 h-0.5 bg-white/20 rounded-full" />
        <span className="text-gray-500 w-16 text-right">CURRENT</span>
      </div>
      {supports.map(s => (
        <div key={s} className="flex items-center gap-3 text-xs">
          <span className="text-green-400 font-bold w-20">${s.toFixed(2)}</span>
          <div className="flex-1 h-1 bg-gray-800 rounded-full">
            <div className="h-1 bg-green-700/60 rounded-full" style={{ width: `${Math.min(Math.abs(current - s) / current * 200 + 30, 92)}%` }} />
          </div>
          <span className="text-green-600 w-16 text-right">-{((current - s) / current * 100).toFixed(1)}% S</span>
        </div>
      ))}
    </div>
  );
};

// ─── Main component ──────────────────────────────────────────────────────────

const TechnicalAnalysisPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAppSelector(s => s.auth);
  const isHe = user?.preferred_language === "he";

  const [rec, setRec]         = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [tradeModal, setTradeModal] = useState<{ type: OrderType } | null>(null);

  const runAnalysis = async (r: Recommendation) => {
    setRunning(true);
    try {
      const result = await recommendationsApi.requestTechnicalAnalysis(r.id);
      setRec(prev => prev ? { ...prev, technical_analysis: result.technical_analysis } : prev);
    } catch {}
    setRunning(false);
  };

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    recommendationsApi.getRecommendation(Number(id)).then(data => {
      setRec(data);
      setLoading(false);
      const ta = data.technical_analysis as TechnicalAnalysis | null;
      const hasFailed = ta?.error || ta?.signal_reasoning?.includes("Analysis failed") || ta?.signal_reasoning?.includes("No current price");
      const hasNoData = ta && (!ta.analysis_breakdown || ta.analysis_breakdown.length === 0) && ta.technical_score === 50;
      if (!ta || hasFailed || hasNoData) runAnalysis(data);
    }).catch(() => navigate("/recommendations"));
  }, [id]);

  const handleConfirmTrade = async (quantity: number, price: number) => {
    if (!rec || !tradeModal) return;
    try {
      await ordersApi.createOrder({ symbol: rec.symbol, order_type: tradeModal.type, quantity, price, recommendation_id: rec.id });
      await recommendationsApi.acknowledgeRecommendation(rec.id);
      setTradeModal(null);
      navigate("/orders");
    } catch (e: any) {
      alert(e.response?.data?.detail || "Order failed");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500" />
      </div>
    );
  }
  if (!rec) return null;

  const ta      = rec.technical_analysis as TechnicalAnalysis | null;
  const isShort = rec.recommendation_type === RecommendationType.SELL || rec.recommendation_type === RecommendationType.STRONG_SELL;
  const signal  = ta?.timing_signal ?? "WAIT";
  const ss      = SIG[signal] ?? SIG.WAIT;
  const score   = ta?.technical_score ?? 50;
  const entry   = rec.current_price_at_recommendation ?? ta?.current_price ?? 0;
  const rrRatio = rec.target_price && rec.stop_loss && entry && Math.abs(entry - rec.stop_loss) > 0
    ? (Math.abs(rec.target_price - entry) / Math.abs(entry - rec.stop_loss)).toFixed(1)
    : null;

  const breakdown     = ta?.analysis_breakdown ?? [];
  const fib           = ta?.fibonacci_levels;
  const wyckoff       = ta?.wyckoff_phase ? (WYCKOFF_LABEL[ta.wyckoff_phase] ?? WYCKOFF_LABEL.UNKNOWN) : null;
  const candlesticks  = ta?.candlestick_patterns ?? [];
  const chartPatterns = ta?.chart_patterns ?? [];

  return (
    <div dir="ltr" className="max-w-7xl mx-auto space-y-4 font-mono">

      {/* Breadcrumb */}
      <div className="flex items-center justify-between">
        <Link to={`/research/${rec.id}`} className="text-xs text-gray-500 hover:text-gray-300 tracking-widest">
          ← RESEARCH · {rec.symbol}
        </Link>
        <span className="text-xs text-gray-700">
          {ta?.analysis_timestamp ? new Date(ta.analysis_timestamp).toLocaleString("en-US") : ""}
        </span>
      </div>

      {/* Signal Banner */}
      <div className={`rounded-2xl border ${ss.border} ${ss.bg} overflow-hidden`}>
        <div className="flex items-center justify-between px-5 py-2.5 bg-black/20 border-b border-white/5">
          <span className="text-xs text-gray-500 tracking-widest">
            TECHNICAL ANALYSIS · {rec.symbol} · {rec.asset_name ?? ""}
          </span>
          <span className={`text-xs px-2 py-0.5 rounded border font-bold ${ss.border} ${ss.text}`}>
            {signal.replace("_", " ")}
          </span>
        </div>
        <div className="px-5 py-4 flex flex-wrap items-center gap-6">
          <div className="flex items-center gap-4">
            <div className={`w-1.5 h-12 rounded-full ${ss.bar}`} />
            <div>
              <p className={`text-4xl font-black tracking-widest ${ss.text}`}>{signal.replace("_", " ")}</p>
              <p className="text-xs text-gray-500 mt-0.5 tracking-wider">
                {ta?.signal_strength ?? "—"} · {ta?.data_source === "info_derived" ? "STATIC ANALYSIS" : ta?.data_bars ? `${ta.data_bars} BARS` : "PENDING"}
              </p>
            </div>
          </div>
          <div className="flex gap-8 ml-auto">
            {rrRatio && (
              <div className="text-center">
                <p className="text-xs text-gray-600 tracking-widest">RISK / REWARD</p>
                <p className="text-2xl font-bold text-white">{rrRatio}<span className="text-gray-500 text-base">×</span></p>
              </div>
            )}
            <div className="text-center">
              <p className="text-xs text-gray-600 tracking-widest">TECH SCORE</p>
              <p className={`text-2xl font-bold ${score >= 62 ? "text-green-400" : score <= 38 ? "text-red-400" : "text-yellow-400"}`}>
                {score.toFixed(0)}<span className="text-gray-600 text-sm">/100</span>
              </p>
            </div>
            {entry > 0 && (
              <div className="text-center">
                <p className="text-xs text-gray-600 tracking-widest">PRICE AT ANALYSIS</p>
                <p className="text-2xl font-bold text-white">${entry.toFixed(2)}</p>
              </div>
            )}
          </div>
        </div>
        <div className="px-5 pb-4">
          <div className="h-1 bg-gray-800/60 rounded-full overflow-hidden">
            <div className={`h-1 rounded-full ${ss.bar}`} style={{ width: `${score}%` }} />
          </div>
        </div>
      </div>

      {running && (
        <div className="bg-blue-950/30 border border-blue-800/30 rounded-xl px-5 py-3 text-xs text-blue-400 tracking-wider flex items-center gap-3">
          <div className="animate-spin w-3 h-3 border border-blue-400 border-t-transparent rounded-full" />
          RUNNING FULL TECHNICAL ANALYSIS — CANDLESTICKS · FIBONACCI · WYCKOFF · INDICATORS…
        </div>
      )}

      {!running && ta?.error && (
        <div className="bg-red-950/20 border border-red-800/30 rounded-xl px-5 py-3 text-xs text-red-400 tracking-wider flex items-center justify-between">
          <span>⚠ PREVIOUS ANALYSIS FAILED: {ta.error} — click RE-RUN ANALYSIS to retry</span>
          <button onClick={() => rec && runAnalysis(rec)} className="ml-4 text-red-300 hover:text-white underline">RE-RUN</button>
        </div>
      )}

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* LEFT: range bar + chart + module list */}
        <div className="lg:col-span-2 space-y-4">

          {/* 52-week range */}
          <div className="bg-gray-900 rounded-2xl border border-gray-800 p-5">
            <p className="text-xs text-gray-600 tracking-widest mb-4">52-WEEK RANGE POSITION</p>
            {ta ? <RangeBar ta={ta} /> : <p className="text-xs text-gray-700 text-center py-4">Awaiting analysis…</p>}
          </div>

          {/* Score breakdown chart */}
          {breakdown.length > 0 && (
            <div className="bg-gray-900 rounded-2xl border border-gray-800 p-5">
              <p className="text-xs text-gray-600 tracking-widest mb-4">SIGNAL BREAKDOWN · SCORE IMPACT PER MODULE</p>
              <BreakdownChart items={breakdown} />
            </div>
          )}

          {/* Module list */}
          {breakdown.length > 0 ? (
            <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">
              <div className="px-5 py-3 border-b border-gray-800">
                <p className="text-xs text-gray-500 tracking-widest">{breakdown.length} ANALYSIS MODULES RUN</p>
              </div>
              {breakdown.map((mod, i) => <ModuleCard key={i} mod={mod} />)}
            </div>
          ) : ta && (
            <div className="bg-gray-900 rounded-2xl border border-gray-800 p-5">
              <p className="text-xs text-gray-600 tracking-widest mb-3">REASONING</p>
              <p className="text-xs text-gray-400 leading-relaxed">{ta.signal_reasoning || "No reasoning available"}</p>
            </div>
          )}
        </div>

        {/* RIGHT: trade params + patterns + fib + levels */}
        <div className="space-y-4">

          {/* Trade parameters */}
          <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">
            <div className="px-4 py-2.5 border-b border-gray-800">
              <p className="text-xs text-gray-600 tracking-widest">TRADE PARAMETERS</p>
            </div>
            <div className="divide-y divide-gray-800/50">
              {[
                { label: "DIRECTION",  value: isShort ? "SHORT" : "LONG",                        cls: isShort ? "text-red-400" : "text-green-400" },
                { label: "ENTRY",      value: entry > 0 ? `$${entry.toFixed(2)}` : "—",          cls: "text-white" },
                { label: "TARGET",     value: rec.target_price ? `$${rec.target_price.toFixed(2)}` : "—", cls: "text-green-400" },
                { label: "STOP",       value: rec.stop_loss ? `$${rec.stop_loss.toFixed(2)}` : "—",       cls: "text-red-400" },
                { label: "R:R",        value: rrRatio ? `${rrRatio}×` : "—",                     cls: "text-white" },
                { label: "CONFIDENCE", value: `${rec.confidence_score.toFixed(0)}%`,              cls: "text-blue-400" },
              ].map(r => (
                <div key={r.label} className="flex items-center justify-between px-4 py-2.5 text-xs">
                  <span className="text-gray-600 tracking-wider">{r.label}</span>
                  <span className={`font-bold ${r.cls}`}>{r.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Wyckoff */}
          {wyckoff && (
            <div className={`rounded-2xl border p-4 ${wyckoff.color}`}>
              <p className="text-xs tracking-widest mb-1 opacity-70">WYCKOFF METHOD</p>
              <p className="font-black text-sm tracking-widest">{wyckoff.label}</p>
              <p className="text-xs mt-1 opacity-60 leading-relaxed">{wyckoff.desc}</p>
            </div>
          )}

          {/* Candlestick patterns */}
          {candlesticks.length > 0 && (
            <div className="bg-gray-900 rounded-2xl border border-gray-800 p-4">
              <p className="text-xs text-gray-600 tracking-widest mb-3">CANDLESTICK PATTERNS</p>
              <div className="flex flex-wrap gap-1.5">
                {candlesticks.map(p => (
                  <span key={p} className={`text-xs px-2 py-1 rounded border font-bold tracking-wider ${
                    p.includes("BULL") || p.includes("HAMMER") || p.includes("MORNING") || p.includes("WHITE")
                      ? "bg-green-950/40 text-green-400 border-green-900/40"
                      : p.includes("BEAR") || p.includes("SHOOTING") || p.includes("EVENING") || p.includes("CROW")
                      ? "bg-red-950/40 text-red-400 border-red-900/40"
                      : "bg-gray-800/60 text-gray-400 border-gray-700/40"
                  }`}>
                    {p.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Chart patterns */}
          {chartPatterns.length > 0 && (
            <div className="bg-gray-900 rounded-2xl border border-gray-800 p-4">
              <p className="text-xs text-gray-600 tracking-widest mb-3">CHART PATTERNS</p>
              <div className="flex flex-wrap gap-1.5">
                {chartPatterns.map(p => (
                  <span key={p} className={`text-xs px-2 py-1 rounded border font-bold tracking-wider ${
                    p.includes("UP") || p.includes("LOW") || p.includes("GOLDEN")
                      ? "bg-green-950/40 text-green-400 border-green-900/40"
                      : p.includes("DOWN") || p.includes("HIGH") || p.includes("DEATH")
                      ? "bg-red-950/40 text-red-400 border-red-900/40"
                      : "bg-gray-800/60 text-gray-400 border-gray-700/40"
                  }`}>
                    {p.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Price levels */}
          {ta && (ta.support_levels?.length > 0 || ta.resistance_levels?.length > 0) && (
            <div className="bg-gray-900 rounded-2xl border border-gray-800 p-4">
              <p className="text-xs text-gray-600 tracking-widest mb-3">KEY LEVELS</p>
              <PriceLevels ta={ta} />
            </div>
          )}

          {/* Fibonacci */}
          {fib && (
            <div className="bg-gray-900 rounded-2xl border border-gray-800 p-4">
              <p className="text-xs text-gray-600 tracking-widest mb-3">FIBONACCI RETRACEMENT</p>
              <FibPanel fib={fib} current={ta?.current_price ?? entry} />
            </div>
          )}

          {/* Re-run */}
          <button
            onClick={() => rec && runAnalysis(rec)}
            disabled={running}
            className="w-full border border-gray-700 hover:border-gray-500 text-gray-400 hover:text-gray-200 rounded-xl py-3 text-xs tracking-widest disabled:opacity-40 transition-colors"
          >
            {running ? "⟳ ANALYZING…" : "⟳ RE-RUN ANALYSIS"}
          </button>
        </div>
      </div>

      {/* Action buttons */}
      <div className="grid grid-cols-2 gap-4">
        <button
          onClick={() => setTradeModal({ type: isShort ? OrderType.SELL : OrderType.BUY })}
          className={`py-4 rounded-2xl font-black text-sm tracking-widest ${
            isShort ? "bg-red-600 hover:bg-red-700 text-white" : "bg-green-600 hover:bg-green-700 text-white"
          }`}
        >
          {isShort ? "▼ OPEN SHORT" : "▲ OPEN LONG"} · {rec.symbol}
        </button>
        <Link
          to={`/research/${rec.id}`}
          className="py-4 rounded-2xl border border-gray-700 hover:border-gray-500 text-gray-300 text-sm tracking-widest text-center font-bold transition-colors flex items-center justify-center"
        >
          FUNDAMENTAL →
        </Link>
      </div>

      {tradeModal && rec && (
        <ConfirmTradeModal
          recommendation={rec}
          orderType={tradeModal.type}
          isHe={isHe}
          onConfirm={handleConfirmTrade}
          onCancel={() => setTradeModal(null)}
        />
      )}
    </div>
  );
};

export default TechnicalAnalysisPage;
