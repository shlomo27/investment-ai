import React, { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell,
} from "recharts";
import { useAppSelector } from "../store";
import { recommendationsApi, ordersApi } from "../api/client";
import { Recommendation, RecommendationType, TechnicalAnalysis, OrderType } from "../types";
import ConfirmTradeModal from "../components/Trading/ConfirmTradeModal";

// ─── Signal colours ───────────────────────────────────────────────────────────

const SIG: Record<string, { bar: string; text: string; bg: string }> = {
  STRONG_BUY:  { bar: "bg-green-500",  text: "text-green-300",  bg: "bg-green-900/20 border-green-700/40" },
  BUY_NOW:     { bar: "bg-green-600",  text: "text-green-400",  bg: "bg-green-950/30 border-green-800/30" },
  WAIT:        { bar: "bg-yellow-500", text: "text-yellow-300", bg: "bg-yellow-900/10 border-yellow-800/30" },
  SELL_NOW:    { bar: "bg-red-600",    text: "text-red-400",    bg: "bg-red-950/30 border-red-800/30" },
  STRONG_SELL: { bar: "bg-red-500",    text: "text-red-300",    bg: "bg-red-900/20 border-red-700/40" },
};

// ─── Indicator score chart ────────────────────────────────────────────────────

interface IndicatorItem {
  name: string;
  score: number;
  bull: boolean;
}

const IndicatorChart: React.FC<{ items: IndicatorItem[] }> = ({ items }) => (
  <ResponsiveContainer width="100%" height={items.length * 36 + 20}>
    <BarChart
      data={items}
      layout="vertical"
      margin={{ top: 0, right: 40, left: 0, bottom: 0 }}
      barSize={12}
    >
      <XAxis type="number" domain={[-25, 25]} hide />
      <YAxis type="category" dataKey="name" width={110} tick={{ fill: "#6b7280", fontSize: 10, fontFamily: "monospace" }} />
      <ReferenceLine x={0} stroke="#374151" />
      <Tooltip
        cursor={{ fill: "#1f293720" }}
        contentStyle={{ background: "#111827", border: "1px solid #374151", borderRadius: 8, fontSize: 11, fontFamily: "monospace" }}
        formatter={(v: number) => [`${v > 0 ? "+" : ""}${v}`, "impact"]}
      />
      <Bar dataKey="score" radius={[0, 4, 4, 0]}>
        {items.map((it, i) => (
          <Cell key={i} fill={it.bull ? "#22c55e" : it.score < 0 ? "#ef4444" : "#eab308"} />
        ))}
      </Bar>
    </BarChart>
  </ResponsiveContainer>
);

// ─── Range bar ────────────────────────────────────────────────────────────────

const RangeBar: React.FC<{ ta: TechnicalAnalysis }> = ({ ta }) => {
  const low  = ta.week52_low  ?? (ta.support_levels?.[0]);
  const high = ta.week52_high ?? (ta.resistance_levels?.[0]);
  const cur  = ta.current_price;
  if (!low || !high || !cur || high <= low) return null;

  const pct = (v: number) => Math.min(Math.max(((v - low) / (high - low)) * 100, 1), 99);
  const curPct   = pct(cur);
  const ma50Pct  = ta.ma_50  ? pct(ta.ma_50)  : null;
  const ma200Pct = ta.ma_200 ? pct(ta.ma_200) : null;

  return (
    <div className="space-y-2">
      <div className="flex justify-between text-xs text-gray-600 font-mono">
        <span>52W LOW  ${low.toFixed(0)}</span>
        <span>52W HIGH  ${high.toFixed(0)}</span>
      </div>
      <div className="relative h-5 bg-gray-800 rounded-full overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-red-900/50 via-yellow-900/30 to-green-900/50" />
        {ma200Pct != null && (
          <div className="absolute top-0 bottom-0 w-px bg-orange-400/60" style={{ left: `${ma200Pct}%` }} />
        )}
        {ma50Pct != null && (
          <div className="absolute top-0 bottom-0 w-px bg-blue-400/60" style={{ left: `${ma50Pct}%` }} />
        )}
        <div
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-4 h-4 bg-white rounded-full shadow shadow-white/40 z-10 border-2 border-gray-900"
          style={{ left: `${curPct}%` }}
        />
      </div>
      <div className="flex justify-between text-xs font-mono">
        {ma200Pct != null && <span className="text-orange-400/70">MA200 ${ta.ma_200?.toFixed(0)}</span>}
        <span className="text-white font-bold mx-auto">${cur.toFixed(2)} NOW</span>
        {ma50Pct != null && <span className="text-blue-400/70">MA50 ${ta.ma_50?.toFixed(0)}</span>}
      </div>
    </div>
  );
};

// ─── Main Page ────────────────────────────────────────────────────────────────

const TechnicalAnalysisPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAppSelector((s) => s.auth);

  const [rec, setRec] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [tradeModal, setTradeModal] = useState<{ type: OrderType } | null>(null);

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        const data = await recommendationsApi.getRecommendation(Number(id));
        setRec(data);
        // Auto-run if no technical analysis yet
        if (!data.technical_analysis) {
          runAnalysis(data);
        }
      } catch {
        navigate("/recommendations");
      }
      setLoading(false);
    })();
  }, [id]);

  const runAnalysis = async (r: Recommendation) => {
    setRunning(true);
    try {
      const result = await recommendationsApi.requestTechnicalAnalysis(r.id);
      setRec((prev) => prev ? { ...prev, technical_analysis: result.technical_analysis } : prev);
    } catch {}
    setRunning(false);
  };

  const handleConfirmTrade = async (quantity: number, price: number) => {
    if (!rec || !tradeModal) return;
    try {
      await ordersApi.createOrder({
        symbol: rec.symbol,
        order_type: tradeModal.type,
        quantity,
        price,
        recommendation_id: rec.id,
      });
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

  const ta = rec.technical_analysis;
  const signal = ta?.timing_signal ?? "WAIT";
  const ss = SIG[signal] ?? SIG.WAIT;
  const score = ta?.technical_score ?? 50;
  const isShort = rec.recommendation_type === RecommendationType.SELL || rec.recommendation_type === RecommendationType.STRONG_SELL;
  const entry = rec.current_price_at_recommendation ?? ta?.current_price;
  const rrRatio = rec.target_price && rec.stop_loss && entry && Math.abs(entry - rec.stop_loss) > 0
    ? (Math.abs(rec.target_price - entry) / Math.abs(entry - rec.stop_loss)).toFixed(1)
    : null;

  // Build indicator score items for chart
  const indicatorItems: IndicatorItem[] = [];
  if (ta) {
    if (ta.ma_trend === "BULLISH")  indicatorItems.push({ name: "MA TREND",   score: 10, bull: true });
    if (ta.ma_trend === "BEARISH")  indicatorItems.push({ name: "MA TREND",   score: -10, bull: false });
    if (ta.macd_crossover === "BULLISH") indicatorItems.push({ name: "MACD",  score: 12, bull: true });
    if (ta.macd_crossover === "BEARISH") indicatorItems.push({ name: "MACD",  score: -12, bull: false });
    if (ta.bb_position != null) {
      if (ta.bb_position < 20)      indicatorItems.push({ name: "BOLLINGER", score: 10, bull: true });
      else if (ta.bb_position > 80) indicatorItems.push({ name: "BOLLINGER", score: -10, bull: false });
    }
    if (ta.rsi_14 != null) {
      if (ta.rsi_14 < 30) indicatorItems.push({ name: "RSI/52W POS", score: 15, bull: true });
      else if (ta.rsi_14 > 70) indicatorItems.push({ name: "RSI/52W POS", score: -8, bull: false });
    }
    if (ta.week52_change_pct != null) {
      const s = Math.min(Math.max(Math.round(ta.week52_change_pct / 4), -20), 20);
      indicatorItems.push({ name: "52W RETURN", score: s, bull: s > 0 });
    }
    if (ta.analyst_consensus_mean != null) {
      const s = ta.analyst_consensus_mean <= 2 ? 10 : ta.analyst_consensus_mean >= 3.5 ? -8 : 0;
      if (s !== 0) indicatorItems.push({ name: "ANALYST", score: s, bull: s > 0 });
    }
    if (ta.short_interest_pct != null && ta.short_interest_pct > 10) {
      indicatorItems.push({ name: "SHORT INT", score: -5, bull: false });
    }
    if (ta.golden_cross) indicatorItems.push({ name: "GOLDEN CROSS", score: 15, bull: true });
    if (ta.death_cross)  indicatorItems.push({ name: "DEATH CROSS",  score: -15, bull: false });
  }

  return (
    <div dir="ltr" className="max-w-5xl mx-auto space-y-5 font-mono">
      {/* Navigation */}
      <div className="flex items-center justify-between">
        <Link to={`/research/${rec.id}`} className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1">
          ← RESEARCH · {rec.symbol}
        </Link>
        <span className="text-xs text-gray-700">
          {ta?.analysis_timestamp
            ? new Date(ta.analysis_timestamp).toLocaleString("en-US", { dateStyle: "short", timeStyle: "short" })
            : "NO ANALYSIS YET"}
        </span>
      </div>

      {/* Header terminal bar */}
      <div className="bg-gray-950 border border-gray-800 rounded-2xl overflow-hidden">
        <div className="bg-gray-900/80 border-b border-gray-800 px-5 py-3 flex items-center justify-between">
          <span className="text-xs text-gray-500 tracking-widest">
            TECHNICAL ANALYSIS · {rec.symbol} · {rec.asset_name ?? ""}
            {ta?.data_source === "info_derived" ? " · STATIC DATA" : ta?.data_bars ? ` · ${ta.data_bars} BARS` : ""}
          </span>
          <span className={`text-xs font-bold px-2 py-0.5 rounded border ${ss.bg}`}>{signal.replace("_", " ")}</span>
        </div>

        {/* Signal + score + R:R row */}
        <div className={`px-6 py-5 border-b border-gray-800 ${ss.bg} border`}>
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-4">
              <div className={`w-1.5 h-14 rounded-full ${ss.bar}`} />
              <div>
                <p className={`text-4xl font-black tracking-widest ${ss.text}`}>{signal.replace("_", " ")}</p>
                <p className="text-xs text-gray-600 mt-1">{ta?.signal_strength ?? "—"} · {rec.symbol} · {rec.sector ?? ""}</p>
              </div>
            </div>
            <div className="flex gap-8 text-right">
              {rrRatio && (
                <div>
                  <p className="text-xs text-gray-600">RISK / REWARD</p>
                  <p className="text-3xl font-bold text-white">{rrRatio}<span className="text-base text-gray-500">×</span></p>
                </div>
              )}
              <div>
                <p className="text-xs text-gray-600">TECH SCORE</p>
                <p className={`text-3xl font-bold ${score >= 60 ? "text-green-400" : score <= 40 ? "text-red-400" : "text-yellow-400"}`}>
                  {score.toFixed(0)}<span className="text-base text-gray-600">/100</span>
                </p>
              </div>
              {rec.current_price_at_recommendation && (
                <div>
                  <p className="text-xs text-gray-600">PRICE AT ANALYSIS</p>
                  <p className="text-3xl font-bold text-white">${rec.current_price_at_recommendation.toFixed(2)}</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Score bar */}
        <div className="h-1.5 bg-gray-800">
          <div
            className={`h-full transition-all duration-700 ${score >= 60 ? "bg-green-500" : score <= 40 ? "bg-red-500" : "bg-yellow-500"}`}
            style={{ width: `${score}%` }}
          />
        </div>
      </div>

      {/* Running / no-data state */}
      {running && (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 flex flex-col items-center gap-3">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
          <p className="text-xs text-gray-500 tracking-widest">RUNNING TECHNICAL ANALYSIS · {rec.symbol}</p>
        </div>
      )}

      {!ta && !running && (
        <div className="bg-gray-900 border border-dashed border-gray-700 rounded-2xl p-10 flex flex-col items-center gap-4">
          <p className="text-gray-500 text-sm">No technical analysis yet</p>
          <button
            onClick={() => runAnalysis(rec)}
            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg font-bold tracking-wide"
          >
            RUN ANALYSIS
          </button>
        </div>
      )}

      {ta && !running && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* LEFT COLUMN */}
          <div className="lg:col-span-2 space-y-5">
            {/* 52-week range */}
            <div className="bg-gray-950 border border-gray-800 rounded-2xl p-5">
              <p className="text-xs text-gray-600 tracking-widest mb-4">52-WEEK RANGE POSITION</p>
              <RangeBar ta={ta} />
              {ta.week52_change_pct != null && (
                <div className="mt-4 flex gap-6 text-xs">
                  <div>
                    <p className="text-gray-600">52W RETURN</p>
                    <p className={`font-bold text-base ${ta.week52_change_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {ta.week52_change_pct >= 0 ? "+" : ""}{ta.week52_change_pct.toFixed(1)}%
                    </p>
                  </div>
                  {ta.rsi_14 != null && (
                    <div>
                      <p className="text-gray-600">52W POSITION</p>
                      <p className={`font-bold text-base ${ta.rsi_14 < 30 ? "text-green-400" : ta.rsi_14 > 70 ? "text-red-400" : "text-white"}`}>
                        {ta.rsi_14.toFixed(0)}%
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Indicator contribution chart */}
            {indicatorItems.length > 0 && (
              <div className="bg-gray-950 border border-gray-800 rounded-2xl p-5">
                <p className="text-xs text-gray-600 tracking-widest mb-4">SIGNAL BREAKDOWN</p>
                <IndicatorChart items={indicatorItems} />
              </div>
            )}

            {/* Reasoning */}
            {ta.signal_reasoning && (
              <div className="bg-gray-950 border border-gray-800 rounded-2xl p-5">
                <p className="text-xs text-gray-600 tracking-widest mb-3">REASONING</p>
                <p className="text-xs text-gray-400 leading-loose">{ta.signal_reasoning}</p>
              </div>
            )}
          </div>

          {/* RIGHT COLUMN */}
          <div className="space-y-5">
            {/* Price levels */}
            {(ta.resistance_levels?.length || ta.support_levels?.length) && ta.current_price && (
              <div className="bg-gray-950 border border-gray-800 rounded-2xl p-5">
                <p className="text-xs text-gray-600 tracking-widest mb-4">KEY LEVELS</p>
                <div className="space-y-2">
                  {(ta.resistance_levels ?? []).slice(0, 3).map((r) => {
                    const d = (((r - ta.current_price!) / ta.current_price!) * 100).toFixed(1);
                    return (
                      <div key={r} className="flex items-center justify-between text-xs">
                        <span className="text-red-400 font-bold">${r.toFixed(2)}</span>
                        <div className="flex-1 mx-3 h-px bg-red-800/40" />
                        <span className="text-red-700">+{d}% R</span>
                      </div>
                    );
                  })}
                  <div className="flex items-center justify-between text-xs border-y border-gray-800 py-2 my-1">
                    <span className="text-white font-bold">${ta.current_price.toFixed(2)}</span>
                    <span className="text-gray-600 text-xs">NOW</span>
                  </div>
                  {(ta.support_levels ?? []).slice(0, 3).map((s) => {
                    const d = (((ta.current_price! - s) / ta.current_price!) * 100).toFixed(1);
                    return (
                      <div key={s} className="flex items-center justify-between text-xs">
                        <span className="text-green-400 font-bold">${s.toFixed(2)}</span>
                        <div className="flex-1 mx-3 h-px bg-green-800/40" />
                        <span className="text-green-700">-{d}% S</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Trade parameters */}
            <div className="bg-gray-950 border border-gray-800 rounded-2xl p-5">
              <p className="text-xs text-gray-600 tracking-widest mb-4">TRADE PARAMETERS</p>
              <div className="space-y-3">
                {[
                  { label: "DIRECTION", val: isShort ? "SHORT" : "LONG", color: isShort ? "text-red-400" : "text-green-400" },
                  { label: "ENTRY", val: entry ? `$${entry.toFixed(2)}` : "—", color: "text-white" },
                  { label: "TARGET", val: rec.target_price ? `$${rec.target_price.toFixed(2)}` : "—", color: isShort ? "text-red-300" : "text-green-300" },
                  { label: "STOP", val: rec.stop_loss ? `$${rec.stop_loss.toFixed(2)}` : "—", color: "text-red-400" },
                  { label: "R:R", val: rrRatio ? `${rrRatio}×` : "—", color: "text-blue-300" },
                  { label: "CONFIDENCE", val: `${rec.confidence_score.toFixed(0)}%`, color: "text-white" },
                ].map((row) => (
                  <div key={row.label} className="flex items-center justify-between text-xs">
                    <span className="text-gray-600">{row.label}</span>
                    <span className={`font-bold ${row.color}`}>{row.val}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Chart patterns */}
            {ta.chart_patterns && ta.chart_patterns.length > 0 && (
              <div className="bg-gray-950 border border-gray-800 rounded-2xl p-5">
                <p className="text-xs text-gray-600 tracking-widest mb-3">PATTERNS</p>
                <div className="flex flex-wrap gap-1.5">
                  {ta.chart_patterns.map((p) => (
                    <span key={p} className={`text-xs px-2 py-0.5 rounded border font-bold ${
                      p.includes("UP") || p.includes("LOW") || p.includes("GOLDEN")
                        ? "bg-green-950/40 text-green-400 border-green-900/40"
                        : "bg-red-950/40 text-red-400 border-red-900/40"
                    }`}>
                      {p.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Re-run button */}
            <button
              onClick={() => runAnalysis(rec)}
              disabled={running}
              className="w-full py-2.5 border border-gray-700 text-gray-500 hover:border-gray-500 hover:text-gray-300 text-xs rounded-xl tracking-widest transition-colors"
            >
              ↺ RE-RUN ANALYSIS
            </button>
          </div>
        </div>
      )}

      {/* Action buttons */}
      {ta && !running && (
        <div className="flex gap-3 pt-2">
          {!isShort ? (
            <button
              onClick={() => setTradeModal({ type: OrderType.BUY })}
              className="flex-1 bg-green-600 hover:bg-green-700 text-white rounded-xl py-3.5 font-bold tracking-widest text-sm"
            >
              ▲ OPEN LONG · {rec.symbol}
            </button>
          ) : (
            <button
              onClick={() => setTradeModal({ type: OrderType.SELL })}
              className="flex-1 bg-red-600 hover:bg-red-700 text-white rounded-xl py-3.5 font-bold tracking-widest text-sm"
            >
              ▼ OPEN SHORT · {rec.symbol}
            </button>
          )}
          <Link
            to={`/research/${rec.id}`}
            className="px-6 border border-gray-700 text-gray-400 rounded-xl hover:border-gray-500 hover:text-gray-200 text-xs flex items-center tracking-widest"
          >
            FUNDAMENTAL →
          </Link>
        </div>
      )}

      {tradeModal && rec && (
        <ConfirmTradeModal
          recommendation={rec}
          orderType={tradeModal.type}
          isHe={user?.preferred_language === "he"}
          onConfirm={handleConfirmTrade}
          onCancel={() => setTradeModal(null)}
        />
      )}
    </div>
  );
};

export default TechnicalAnalysisPage;
