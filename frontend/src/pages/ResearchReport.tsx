import React, { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useAppSelector } from "../store";
import { recommendationsApi, ordersApi } from "../api/client";
import { Recommendation, RecommendationType, TechnicalAnalysis, OrderType } from "../types";
import ConfirmTradeModal from "../components/Trading/ConfirmTradeModal";

// ─── Helpers ────────────────────────────────────────────────────────────────────

const recColor = (type: string) => {
  if (type === "STRONG_BUY") return "bg-green-500/20 text-green-300 border-green-600/40";
  if (type === "BUY") return "bg-green-900/30 text-green-400 border-green-700/40";
  if (type === "STRONG_SELL") return "bg-red-500/20 text-red-300 border-red-600/40";
  if (type === "SELL") return "bg-red-900/30 text-red-400 border-red-700/40";
  return "bg-gray-800 text-gray-300 border-gray-700";
};

const directionBadge = (bias?: string) => {
  if (bias === "LONG") return "bg-green-900/40 text-green-300 border border-green-700/40";
  if (bias === "SHORT") return "bg-red-900/40 text-red-300 border border-red-700/40";
  return "bg-gray-800 text-gray-400 border border-gray-700";
};

const ScoreBar: React.FC<{ value: number; max?: number; color?: string }> = ({
  value, max = 100, color = "bg-blue-500",
}) => (
  <div className="flex items-center gap-2">
    <div className="flex-1 bg-gray-800 rounded-full h-1.5">
      <div className={`${color} h-1.5 rounded-full`} style={{ width: `${(value / max) * 100}%` }} />
    </div>
    <span className="text-xs text-gray-300 w-8 text-right">{value.toFixed(0)}</span>
  </div>
);

// ─── Technical Terminal Component ────────────────────────────────────────────────

const SIG_STYLE: Record<string, { bar: string; text: string; glow: string }> = {
  STRONG_BUY:  { bar: "bg-green-500",  text: "text-green-300",  glow: "shadow-green-500/30" },
  BUY_NOW:     { bar: "bg-green-600",  text: "text-green-400",  glow: "shadow-green-600/20" },
  WAIT:        { bar: "bg-yellow-600", text: "text-yellow-300", glow: "shadow-yellow-600/20" },
  SELL_NOW:    { bar: "bg-red-600",    text: "text-red-400",    glow: "shadow-red-600/20" },
  STRONG_SELL: { bar: "bg-red-500",    text: "text-red-300",    glow: "shadow-red-500/30" },
};

const TechnicalTerminal: React.FC<{
  ta: TechnicalAnalysis;
  rec: Recommendation;
  isHe: boolean;
}> = ({ ta, rec }) => {
  const signal = ta.timing_signal ?? "WAIT";
  const ss = SIG_STYLE[signal] ?? SIG_STYLE.WAIT;
  const score = ta.technical_score ?? 50;

  const entry = rec.current_price_at_recommendation ?? ta.current_price;
  const target = rec.target_price;
  const stop = rec.stop_loss;
  const rrRatio = target && stop && entry && Math.abs(entry - stop) > 0
    ? (Math.abs(target - entry) / Math.abs(entry - stop)).toFixed(1)
    : null;

  const isInfoDerived = ta.data_source === "info_derived";
  const current = ta.current_price;

  // 52-week range bar position
  const low52 = ta.week52_low ?? (ta.support_levels?.[0]);
  const high52 = ta.week52_high ?? (ta.resistance_levels?.[0]);
  const rangeWidth = (high52 && low52 && high52 > low52) ? high52 - low52 : null;
  const currentPct = rangeWidth && current ? ((current - low52!) / rangeWidth) * 100 : null;
  const ma50Pct    = rangeWidth && ta.ma_50  && low52 ? ((ta.ma_50  - low52) / rangeWidth) * 100 : null;
  const ma200Pct   = rangeWidth && ta.ma_200 && low52 ? ((ta.ma_200 - low52) / rangeWidth) * 100 : null;

  // Indicators table rows
  const rows: { label: string; value: string; bull: boolean | null }[] = [];

  if (ta.ma_trend) rows.push({
    label: "MA TREND",
    value: ta.ma_trend === "BULLISH" ? "50MA > 200MA ↑" : "50MA < 200MA ↓",
    bull: ta.ma_trend === "BULLISH",
  });
  if (ta.macd_crossover && ta.macd_crossover !== "NONE") rows.push({
    label: "MACD",
    value: ta.macd_crossover === "BULLISH" ? "BULLISH CROSS ↑" : "BEARISH CROSS ↓",
    bull: ta.macd_crossover === "BULLISH",
  });
  if (ta.bb_position != null) rows.push({
    label: "BB POSITION",
    value: ta.bb_position < 20 ? "NEAR LOWER BAND" : ta.bb_position > 80 ? "NEAR UPPER BAND" : `MID BAND (${ta.bb_position.toFixed(0)}%)`,
    bull: ta.bb_position < 30,
  });
  if (ta.week52_change_pct != null) rows.push({
    label: "52W RETURN",
    value: `${ta.week52_change_pct >= 0 ? "+" : ""}${ta.week52_change_pct.toFixed(1)}%`,
    bull: ta.week52_change_pct > 0,
  });
  if (ta.analyst_consensus_mean != null) rows.push({
    label: "ANALYST",
    value: ta.analyst_consensus_mean <= 2 ? `STRONG BUY (${ta.analyst_consensus_mean.toFixed(1)})` :
           ta.analyst_consensus_mean <= 2.5 ? `BUY (${ta.analyst_consensus_mean.toFixed(1)})` :
           ta.analyst_consensus_mean >= 3.5 ? `HOLD/SELL (${ta.analyst_consensus_mean.toFixed(1)})` :
           `HOLD (${ta.analyst_consensus_mean.toFixed(1)})`,
    bull: ta.analyst_consensus_mean <= 2.5,
  });
  if (ta.short_interest_pct != null) rows.push({
    label: "SHORT INT",
    value: `${ta.short_interest_pct.toFixed(1)}% FLOAT`,
    bull: ta.short_interest_pct < 5,
  });
  if (ta.volume_ratio != null) rows.push({
    label: "VOLUME",
    value: `${ta.volume_ratio.toFixed(1)}x AVG`,
    bull: ta.volume_ratio > 1,
  });

  return (
    <div dir="ltr" className="bg-gray-950 rounded-2xl border border-gray-800 overflow-hidden font-mono text-sm">
      {/* ── Header bar ── */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-gray-900/80 border-b border-gray-800">
        <span className="text-xs text-gray-500 tracking-widest">
          TECHNICAL · {ta.symbol ?? rec.symbol}
          {isInfoDerived ? " · STATIC" : ta.data_bars ? ` · ${ta.data_bars} BARS` : ""}
        </span>
        <span className="text-xs text-gray-700">
          {ta.analysis_timestamp ? new Date(ta.analysis_timestamp).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }) : ""}
        </span>
      </div>

      {/* ── Signal banner ── */}
      <div className={`px-5 py-4 border-b border-gray-800 flex items-center justify-between ${ss.glow} shadow-lg`}>
        <div className="flex items-center gap-4">
          <div className={`w-1.5 h-10 rounded-full ${ss.bar}`} />
          <div>
            <p className={`text-2xl font-black tracking-widest ${ss.text}`}>
              {signal.replace("_", " ")}
            </p>
            <p className="text-xs text-gray-600 mt-0.5">{ta.signal_strength} · {isInfoDerived ? "STATIC ANALYSIS" : "CHART ANALYSIS"}</p>
          </div>
        </div>
        <div className="text-right space-y-1">
          {rrRatio && (
            <div>
              <span className="text-xs text-gray-600">R:R </span>
              <span className="text-xl font-bold text-white">{rrRatio}×</span>
            </div>
          )}
          <div>
            <span className="text-xs text-gray-600">SCORE </span>
            <span className={`text-xl font-bold ${score >= 60 ? "text-green-400" : score <= 40 ? "text-red-400" : "text-yellow-400"}`}>
              {score.toFixed(0)}
            </span>
            <span className="text-xs text-gray-600">/100</span>
          </div>
        </div>
      </div>

      <div className="p-5 space-y-5">
        {/* ── 52-week range bar ── */}
        {currentPct != null && low52 && high52 && (
          <div>
            <div className="flex justify-between text-xs text-gray-600 mb-1.5">
              <span>52W LOW ${low52.toFixed(0)}</span>
              <span className="text-gray-400">52W RANGE</span>
              <span>52W HIGH ${high52.toFixed(0)}</span>
            </div>
            <div className="relative h-4 bg-gray-800 rounded-full overflow-visible">
              {/* gradient fill */}
              <div
                className="absolute left-0 top-0 h-full rounded-full bg-gradient-to-r from-red-800/60 via-yellow-800/40 to-green-800/60"
                style={{ width: "100%" }}
              />
              {/* MA200 marker */}
              {ma200Pct != null && (
                <div
                  className="absolute top-0 w-0.5 h-4 bg-orange-500/70"
                  style={{ left: `${Math.min(Math.max(ma200Pct, 0), 100)}%` }}
                  title={`MA200 $${ta.ma_200?.toFixed(0)}`}
                />
              )}
              {/* MA50 marker */}
              {ma50Pct != null && (
                <div
                  className="absolute top-0 w-0.5 h-4 bg-blue-400/70"
                  style={{ left: `${Math.min(Math.max(ma50Pct, 0), 100)}%` }}
                  title={`MA50 $${ta.ma_50?.toFixed(0)}`}
                />
              )}
              {/* Current price dot */}
              <div
                className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 bg-white rounded-full shadow-lg shadow-white/30 z-10"
                style={{ left: `${Math.min(Math.max(currentPct, 2), 98)}%` }}
              />
            </div>
            <div className="flex justify-between text-xs mt-1.5">
              {ma200Pct != null && (
                <span className="text-orange-500/70">▲ MA200 ${ta.ma_200?.toFixed(0)}</span>
              )}
              <span className="text-white font-bold mx-auto">${current?.toFixed(2)}</span>
              {ma50Pct != null && (
                <span className="text-blue-400/70">MA50 ${ta.ma_50?.toFixed(0)} ▲</span>
              )}
            </div>
          </div>
        )}

        {/* ── Indicators table ── */}
        {rows.length > 0 && (
          <div className="border border-gray-800 rounded-xl overflow-hidden">
            {rows.map((r, i) => (
              <div key={r.label} className={`flex items-center gap-3 px-4 py-2.5 ${i % 2 === 0 ? "bg-gray-900/40" : ""}`}>
                <span className="text-xs text-gray-600 w-24 flex-shrink-0 tracking-wider">{r.label}</span>
                <div className={`w-1 h-4 rounded-full flex-shrink-0 ${
                  r.bull === true ? "bg-green-500" : r.bull === false ? "bg-red-500" : "bg-gray-600"
                }`} />
                <span className={`text-xs font-bold ${
                  r.bull === true ? "text-green-300" : r.bull === false ? "text-red-300" : "text-gray-400"
                }`}>{r.value}</span>
              </div>
            ))}
          </div>
        )}

        {/* ── Price levels ── */}
        {(ta.resistance_levels?.length || ta.support_levels?.length) && current && (
          <div>
            <p className="text-xs text-gray-600 tracking-widest mb-2">KEY LEVELS</p>
            <div className="space-y-1">
              {(ta.resistance_levels ?? []).slice(0, 2).map((r) => {
                const pct = (((r - current) / current) * 100).toFixed(1);
                const w = Math.min(Math.abs(r - current) / current * 200 + 40, 95);
                return (
                  <div key={r} className="flex items-center gap-3 text-xs">
                    <span className="text-red-400 font-bold w-20">${r.toFixed(2)}</span>
                    <div className="flex-1 h-1 bg-gray-800 rounded-full">
                      <div className="h-1 bg-red-700/60 rounded-full" style={{ width: `${w}%` }} />
                    </div>
                    <span className="text-red-600 w-14 text-right">+{pct}% R</span>
                  </div>
                );
              })}
              <div className="flex items-center gap-3 text-xs py-0.5">
                <span className="text-white font-bold w-20">${current.toFixed(2)}</span>
                <div className="flex-1 h-0.5 bg-white/20 rounded-full" />
                <span className="text-gray-500 w-14 text-right">NOW</span>
              </div>
              {(ta.support_levels ?? []).slice(0, 2).map((s) => {
                const pct = (((current - s) / current) * 100).toFixed(1);
                const w = Math.min(Math.abs(current - s) / current * 200 + 40, 95);
                return (
                  <div key={s} className="flex items-center gap-3 text-xs">
                    <span className="text-green-400 font-bold w-20">${s.toFixed(2)}</span>
                    <div className="flex-1 h-1 bg-gray-800 rounded-full">
                      <div className="h-1 bg-green-700/60 rounded-full" style={{ width: `${w}%` }} />
                    </div>
                    <span className="text-green-600 w-14 text-right">-{pct}% S</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Chart patterns ── */}
        {ta.chart_patterns && ta.chart_patterns.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {ta.chart_patterns.map((p) => (
              <span key={p} className={`text-xs px-2 py-0.5 rounded tracking-wider font-bold border ${
                p.includes("UP") || p.includes("LOW") || p.includes("GOLDEN")
                  ? "bg-green-950/40 text-green-400/80 border-green-900/40"
                  : p.includes("DOWN") || p.includes("HIGH") || p.includes("DEATH")
                  ? "bg-red-950/40 text-red-400/80 border-red-900/40"
                  : "bg-gray-800/60 text-gray-500 border-gray-700/40"
              }`}>
                {p.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        )}

        {/* ── Reasoning ── */}
        {ta.signal_reasoning && (
          <div className="border-t border-gray-800/60 pt-4">
            <p className="text-xs text-gray-700 tracking-widest mb-1">REASONING</p>
            <p className="text-xs text-gray-500 leading-relaxed">{ta.signal_reasoning}</p>
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Component ───────────────────────────────────────────────────────────────────

const ResearchReport: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAppSelector((s) => s.auth);
  const isHe = user?.preferred_language === "he";

  const [rec, setRec] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(true);
  const [tradeModal, setTradeModal] = useState<{ type: OrderType } | null>(null);
  const [technicalLoading, setTechnicalLoading] = useState(false);

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        const data = await recommendationsApi.getRecommendation(Number(id));
        setRec(data);
      } catch {
        navigate("/recommendations");
      }
      setLoading(false);
    })();
  }, [id]);

  const handleRequestTechnical = async () => {
    if (!rec) return;
    setTechnicalLoading(true);
    try {
      const result = await recommendationsApi.requestTechnicalAnalysis(rec.id);
      setRec((prev) => prev ? { ...prev, technical_analysis: result.technical_analysis } : prev);
    } catch {}
    setTechnicalLoading(false);
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

  const fa = rec.fundamental_analysis;
  const isShort = rec.recommendation_type === RecommendationType.SELL || rec.recommendation_type === RecommendationType.STRONG_SELL;
  // Infer direction from recommendation type when direction_bias is absent or NEUTRAL
  const rawBias = fa?.direction_bias;
  const bias = rawBias && rawBias !== "NEUTRAL"
    ? rawBias
    : isShort ? "SHORT" : "LONG";
  const currentPrice = rec.current_price_at_recommendation;

  const returnPct = rec.expected_return_pct ?? fa?.expected_return_pct;
  const returnPositive = (returnPct || 0) >= 0;

  const triggerBadgeText = () => {
    if (rec.trigger_type === "PRICE_ALERT") return { text: isHe ? "תנועת מחיר" : "Price Alert", cls: "bg-orange-900/30 text-orange-300" };
    if (rec.trigger_type === "NEWS_ALERT") return { text: isHe ? "חדשות" : "News Alert", cls: "bg-purple-900/30 text-purple-300" };
    if (rec.trigger_type === "EARNINGS") return { text: isHe ? "דוח רבעוני" : "Earnings", cls: "bg-blue-900/30 text-blue-300" };
    return null;
  };
  const trigger = triggerBadgeText();

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="max-w-4xl mx-auto space-y-6">
      {/* Back */}
      <Link to="/recommendations" className="text-sm text-gray-400 hover:text-gray-200 flex items-center gap-1">
        ← {isHe ? "חזור להמלצות" : "Back to Recommendations"}
      </Link>

      {/* Hero Header */}
      <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 flex-wrap mb-2">
              <h1 className="text-3xl font-bold font-mono">{rec.symbol}</h1>
              <span className={`px-3 py-1 rounded-lg text-sm font-bold border ${recColor(rec.recommendation_type)}`}>
                {rec.recommendation_type.replace("_", " ")}
              </span>
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${directionBadge(bias)}`}>
                {bias}
              </span>
              {trigger && (
                <span className={`px-2 py-0.5 rounded text-xs ${trigger.cls}`}>{trigger.text}</span>
              )}
            </div>
            {rec.asset_name && <p className="text-gray-400 text-sm">{rec.asset_name}</p>}
            {rec.sector && <p className="text-xs text-gray-500 mt-0.5">{rec.sector}</p>}
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-500">{isHe ? "מחיר בעת ניתוח" : "Price at analysis"}</p>
            <p className="text-2xl font-bold">{currentPrice ? `$${currentPrice.toFixed(2)}` : "—"}</p>
            <p className="text-xs text-gray-500 mt-1">
              {new Date(rec.created_at).toLocaleString(isHe ? "he-IL" : "en-US")}
            </p>
          </div>
        </div>

        {/* Key Numbers Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
          <div>
            <p className="text-xs text-gray-500">{isHe ? "ביטחון" : "Confidence"}</p>
            <ScoreBar value={rec.confidence_score} color={isShort ? "bg-red-500" : "bg-green-500"} />
            <p className="text-sm font-bold mt-0.5">{rec.confidence_score.toFixed(0)}%</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">{isShort ? (isHe ? "יעד שורט" : "Short Target") : (isHe ? "מחיר יעד" : "Target Price")}</p>
            <p className="text-sm font-bold">{rec.target_price ? `$${rec.target_price.toFixed(2)}` : "—"}</p>
            {currentPrice && rec.target_price && (
              <p className={`text-xs ${isShort ? "text-red-400" : "text-green-400"}`}>
                {(((rec.target_price - currentPrice) / currentPrice) * 100).toFixed(1)}%
              </p>
            )}
          </div>
          <div>
            <p className="text-xs text-gray-500">{isHe ? "סטופ לוס" : "Stop Loss"}</p>
            <p className="text-sm font-bold">{rec.stop_loss ? `$${rec.stop_loss.toFixed(2)}` : "—"}</p>
            {currentPrice && rec.stop_loss && (
              <p className="text-xs text-gray-400">
                {(((rec.stop_loss - currentPrice) / currentPrice) * 100).toFixed(1)}%
              </p>
            )}
          </div>
          <div>
            <p className="text-xs text-gray-500">{isHe ? "תשואה צפויה" : "Expected Return"}</p>
            <p className={`text-sm font-bold ${returnPositive ? "text-green-400" : "text-red-400"}`}>
              {returnPct != null ? `${returnPct >= 0 ? "+" : ""}${returnPct.toFixed(1)}%` : "—"}
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-3 mt-6">
          {!isShort ? (
            <button
              onClick={() => setTradeModal({ type: OrderType.BUY })}
              className="flex-1 bg-green-600 hover:bg-green-700 text-white rounded-xl py-3 font-medium"
            >
              {isHe ? "פתח פוזיציית LONG" : "Open LONG Position"}
            </button>
          ) : (
            <button
              onClick={() => setTradeModal({ type: OrderType.SELL })}
              className="flex-1 bg-red-600 hover:bg-red-700 text-white rounded-xl py-3 font-medium"
            >
              {isHe ? "פתח פוזיציית SHORT" : "Open SHORT Position"}
            </button>
          )}
          {!rec.technical_analysis && (
            <button
              onClick={handleRequestTechnical}
              disabled={technicalLoading}
              className="flex-1 border border-blue-700 text-blue-400 hover:text-blue-300 rounded-xl py-3 text-sm disabled:opacity-50"
            >
              {technicalLoading ? (isHe ? "מבצע ניתוח..." : "Analyzing...") : (isHe ? "ניתוח טכני" : "Technical Analysis")}
            </button>
          )}
        </div>
      </div>

      {/* Investment Thesis */}
      {fa?.thesis && (
        <div className={`rounded-2xl p-6 border ${isShort ? "bg-red-950/20 border-red-900/30" : "bg-green-950/20 border-green-900/30"}`}>
          <h2 className="font-bold text-sm uppercase tracking-wide mb-3 text-gray-400">
            {isHe ? "תזה להשקעה" : "Investment Thesis"}
          </h2>
          <p className="text-gray-200 leading-relaxed">{fa.thesis}</p>
        </div>
      )}

      {/* Short Catalysts */}
      {isShort && fa?.short_catalysts && fa.short_catalysts.length > 0 && (
        <div className="bg-red-950/20 rounded-2xl p-6 border border-red-900/30">
          <h2 className="font-bold text-sm uppercase tracking-wide mb-3 text-red-400">
            {isHe ? "קטליזטורים לירידה" : "Downside Catalysts"}
          </h2>
          <ul className="space-y-2">
            {fa.short_catalysts.map((c, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                <span className="text-red-400 mt-0.5">▼</span>
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Fundamental Analysis */}
      {fa && (
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-5">
          <h2 className="font-bold">{isHe ? "ניתוח בסיסי — הפקיד" : "Fundamental Analysis"}</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Assessment Badges */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">{isHe ? "הערכת שווי" : "Valuation"}</span>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  fa.valuation_assessment === "UNDERVALUED" ? "bg-green-900/40 text-green-400" :
                  fa.valuation_assessment === "OVERVALUED" ? "bg-red-900/40 text-red-400" :
                  "bg-gray-800 text-gray-400"
                }`}>
                  {fa.valuation_assessment}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">{isHe ? "בריאות פיננסית" : "Financial Health"}</span>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  fa.financial_health === "EXCELLENT" || fa.financial_health === "GOOD" ? "bg-green-900/40 text-green-400" :
                  fa.financial_health === "POOR" ? "bg-red-900/40 text-red-400" :
                  "bg-yellow-900/40 text-yellow-400"
                }`}>
                  {fa.financial_health}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">{isHe ? "אופק השקעה" : "Horizon"}</span>
                <span className="text-xs text-gray-300 bg-gray-800 px-2 py-0.5 rounded">
                  {fa.investment_horizon?.replace("_", " ")}
                </span>
              </div>
            </div>

            {/* Key Metrics */}
            {fa.key_metrics_summary && (
              <div className="space-y-1.5 text-xs text-gray-300">
                {Object.entries(fa.key_metrics_summary).map(([k, v]) => v && (
                  <div key={k}>
                    <span className="text-gray-500">{k.replace(/_/g, " ")}: </span>
                    {v as string}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Bull / Bear */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-green-950/20 rounded-xl p-4 border border-green-900/20">
              <p className="text-xs font-bold text-green-400 mb-2">{isHe ? "תרחיש חיובי" : "Bull Case"}</p>
              <p className="text-sm text-gray-300">{fa.bull_case}</p>
            </div>
            <div className="bg-red-950/20 rounded-xl p-4 border border-red-900/20">
              <p className="text-xs font-bold text-red-400 mb-2">{isHe ? "תרחיש שלילי" : "Bear Case"}</p>
              <p className="text-sm text-gray-300">{fa.bear_case}</p>
            </div>
          </div>

          {/* Catalysts & Risk Factors */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {fa.catalysts && fa.catalysts.length > 0 && (
              <div>
                <p className="text-xs font-bold text-gray-400 mb-2">{isHe ? "קטליזטורים חיוביים" : "Positive Catalysts"}</p>
                <ul className="space-y-1">
                  {fa.catalysts.map((c, i) => (
                    <li key={i} className="text-xs text-gray-300 flex items-start gap-1.5">
                      <span className="text-green-400 mt-0.5">+</span>{c}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {fa.risk_factors && fa.risk_factors.length > 0 && (
              <div>
                <p className="text-xs font-bold text-gray-400 mb-2">{isHe ? "גורמי סיכון" : "Risk Factors"}</p>
                <ul className="space-y-1">
                  {fa.risk_factors.map((r, i) => (
                    <li key={i} className="text-xs text-gray-300 flex items-start gap-1.5">
                      <span className="text-red-400 mt-0.5">!</span>{r}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Analyst Notes */}
          {fa.analyst_notes && (
            <div>
              <p className="text-xs font-bold text-gray-400 mb-2">{isHe ? "הערות אנליסט" : "Analyst Notes"}</p>
              <p className="text-sm text-gray-300 leading-relaxed">{fa.analyst_notes}</p>
            </div>
          )}

          {fa.sector_comparison && (
            <div>
              <p className="text-xs font-bold text-gray-400 mb-1">{isHe ? "השוואה לסקטור" : "Sector Comparison"}</p>
              <p className="text-sm text-gray-300">{fa.sector_comparison}</p>
            </div>
          )}
        </div>
      )}

      {/* Senior Committee Decision */}
      {(rec.senior_notes || rec.senior_review_notes) && (
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <h2 className="font-bold mb-3">{isHe ? "ועדת הבכיר — החלטה סופית" : "Senior Committee — Final Decision"}</h2>
          {rec.senior_review_notes && (
            <div className="mb-3">
              <p className="text-xs text-gray-500 mb-1">{isHe ? "אישור" : "Approval Reasoning"}</p>
              <p className="text-sm text-gray-300">{rec.senior_review_notes}</p>
            </div>
          )}
          {rec.senior_notes && (
            <div>
              <p className="text-xs text-gray-500 mb-1">{isHe ? "הערות ועדה" : "Committee Notes"}</p>
              <p className="text-sm text-gray-300">{rec.senior_notes}</p>
            </div>
          )}
        </div>
      )}

      {/* Technical Analysis — Terminal Style */}
      {rec.technical_analysis
        ? <TechnicalTerminal ta={rec.technical_analysis} rec={rec} isHe={isHe} />
        : (
          <div className="bg-gray-900 rounded-2xl border border-gray-800 border-dashed flex flex-col items-center justify-center py-10 gap-3">
            <p className="text-gray-500 text-sm">{isHe ? "ניתוח טכני טרם בוצע" : "Technical analysis not yet run"}</p>
            <button
              onClick={handleRequestTechnical}
              disabled={technicalLoading}
              className="px-5 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white text-sm rounded-lg font-medium transition-colors"
            >
              {technicalLoading
                ? (isHe ? "מריץ ניתוח..." : "Running analysis...")
                : (isHe ? "הרץ ניתוח טכני" : "Run Technical Analysis")}
            </button>
          </div>
        )
      }

      {/* Trade Modal */}
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

export default ResearchReport;
