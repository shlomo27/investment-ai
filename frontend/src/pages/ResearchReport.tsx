import React, { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer } from "recharts";
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

const RsiGauge: React.FC<{ value: number }> = ({ value }) => {
  const color = value > 70 ? "#f87171" : value < 30 ? "#4ade80" : "#60a5fa";
  const data = [{ value, fill: color }];
  return (
    <ResponsiveContainer width="100%" height={90}>
      <RadialBarChart
        cx="50%" cy="80%"
        innerRadius="70%" outerRadius="100%"
        startAngle={180} endAngle={0}
        data={data}
      >
        <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
        <RadialBar dataKey="value" cornerRadius={4} background={{ fill: "#1f2937" }} />
      </RadialBarChart>
    </ResponsiveContainer>
  );
};

const SignalColor = {
  STRONG_BUY: { bg: "bg-green-500/20", border: "border-green-500/50", text: "text-green-300", dot: "bg-green-400" },
  BUY_NOW:    { bg: "bg-green-900/20", border: "border-green-700/40", text: "text-green-400", dot: "bg-green-500" },
  WAIT:       { bg: "bg-yellow-900/20", border: "border-yellow-700/40", text: "text-yellow-300", dot: "bg-yellow-400" },
  SELL_NOW:   { bg: "bg-red-900/20", border: "border-red-700/40", text: "text-red-400", dot: "bg-red-500" },
  STRONG_SELL:{ bg: "bg-red-500/20", border: "border-red-500/50", text: "text-red-300", dot: "bg-red-400" },
} as const;

const TechnicalTerminal: React.FC<{
  ta: TechnicalAnalysis;
  rec: Recommendation;
  isHe: boolean;
}> = ({ ta, rec, isHe }) => {
  const signal = (ta.timing_signal ?? "WAIT") as keyof typeof SignalColor;
  const sc = SignalColor[signal] ?? SignalColor.WAIT;

  // R:R ratio from recommendation
  const entry = rec.current_price_at_recommendation ?? ta.current_price;
  const target = rec.target_price;
  const stop = rec.stop_loss;
  const rrRatio = target && stop && entry
    ? Math.abs(target - entry) / Math.abs(entry - stop)
    : null;

  const rsi = ta.rsi_14;
  const score = ta.technical_score ?? 50;

  const macdLabel = ta.macd_crossover === "BULLISH" ? "BULLISH CROSS ↑"
    : ta.macd_crossover === "BEARISH" ? "BEARISH CROSS ↓"
    : ta.macd_histogram != null
      ? (ta.macd_histogram > 0 ? "POSITIVE" : "NEGATIVE")
      : "—";

  const bbLabel = ta.bb_position != null
    ? ta.bb_position < 20 ? "NEAR LOWER BAND"
    : ta.bb_position > 80 ? "NEAR UPPER BAND"
    : "MID BAND"
    : "—";

  const maLabel = ta.ma_trend === "BULLISH" ? "ABOVE MA50/200 ↑"
    : ta.ma_trend === "BEARISH" ? "BELOW MA50/200 ↓"
    : "—";

  const hasError = !!ta.error;

  return (
    <div className="bg-gray-950 rounded-2xl border border-gray-800 overflow-hidden font-mono">
      {/* Terminal Header */}
      <div className="bg-gray-900 border-b border-gray-800 px-5 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex gap-1.5">
            <span className="w-3 h-3 rounded-full bg-red-500/70" />
            <span className="w-3 h-3 rounded-full bg-yellow-500/70" />
            <span className="w-3 h-3 rounded-full bg-green-500/70" />
          </div>
          <span className="text-xs text-gray-500">
            TECHNICAL · {ta.symbol ?? rec.symbol}
            {ta.data_bars != null && ` · ${ta.data_bars} BARS`}
          </span>
        </div>
        <span className="text-xs text-gray-600">
          {ta.analysis_timestamp ? new Date(ta.analysis_timestamp).toLocaleTimeString() : ""}
        </span>
      </div>

      <div className="p-5 space-y-5">
        {/* Error state */}
        {hasError && (
          <div className="bg-red-950/30 border border-red-800/40 rounded-xl p-4 text-sm text-red-300">
            ⚠ {ta.signal_reasoning}
          </div>
        )}

        {/* Row 1: Signal card + RSI gauge + score bar */}
        <div className="grid grid-cols-3 gap-4">
          {/* Signal */}
          <div className={`col-span-1 rounded-xl border ${sc.bg} ${sc.border} p-4 flex flex-col items-center justify-center`}>
            <div className={`w-2 h-2 rounded-full ${sc.dot} mb-2 animate-pulse`} />
            <p className={`text-lg font-bold tracking-widest ${sc.text}`}>{signal.replace("_", " ")}</p>
            {rrRatio != null && (
              <p className="text-xs text-gray-400 mt-1">{rrRatio.toFixed(1)} R:R</p>
            )}
            <p className="text-xs text-gray-600 mt-2">{ta.signal_strength}</p>
          </div>

          {/* RSI Gauge */}
          <div className="col-span-1 bg-gray-900 rounded-xl border border-gray-800 p-3 flex flex-col items-center">
            <p className="text-xs text-gray-500 mb-1">RSI 14</p>
            {rsi != null ? (
              <>
                <RsiGauge value={rsi} />
                <p className={`text-xl font-bold -mt-4 ${rsi > 70 ? "text-red-400" : rsi < 30 ? "text-green-400" : "text-white"}`}>
                  {rsi.toFixed(1)}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  {rsi > 70 ? "OVERBOUGHT" : rsi < 30 ? "OVERSOLD" : "NEUTRAL"}
                </p>
              </>
            ) : (
              <p className="text-gray-600 text-sm mt-4">—</p>
            )}
          </div>

          {/* Technical Score */}
          <div className="col-span-1 bg-gray-900 rounded-xl border border-gray-800 p-4 flex flex-col justify-between">
            <p className="text-xs text-gray-500">{isHe ? "ציון טכני" : "Tech Score"}</p>
            <div>
              <p className="text-3xl font-bold text-white">{score.toFixed(0)}</p>
              <p className="text-xs text-gray-600">/100</p>
            </div>
            <div className="w-full bg-gray-800 rounded-full h-1.5 mt-2">
              <div
                className={`h-1.5 rounded-full ${score >= 62 ? "bg-green-500" : score <= 38 ? "bg-red-500" : "bg-yellow-500"}`}
                style={{ width: `${score}%` }}
              />
            </div>
          </div>
        </div>

        {/* Row 2: Indicator grid */}
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "MACD", value: macdLabel, color: ta.macd_crossover === "BULLISH" ? "text-green-400" : ta.macd_crossover === "BEARISH" ? "text-red-400" : "text-gray-300" },
            { label: "BOLLINGER", value: bbLabel, color: ta.bb_position != null && (ta.bb_position < 20 || ta.bb_position > 80) ? "text-yellow-400" : "text-gray-300" },
            { label: "MA TREND", value: maLabel, color: ta.ma_trend === "BULLISH" ? "text-green-400" : ta.ma_trend === "BEARISH" ? "text-red-400" : "text-gray-300" },
          ].map((ind) => (
            <div key={ind.label} className="bg-gray-900/80 border border-gray-800 rounded-lg p-3">
              <p className="text-xs text-gray-600 mb-1">{ind.label}</p>
              <p className={`text-xs font-bold ${ind.color}`}>{ind.value}</p>
            </div>
          ))}
        </div>

        {/* Row 3: Price ladder — support/resistance */}
        {(ta.resistance_levels?.length || ta.support_levels?.length || ta.nearest_resistance || ta.nearest_support) && (
          <div className="bg-gray-900/60 border border-gray-800 rounded-xl p-4">
            <p className="text-xs text-gray-500 mb-3">{isHe ? "רמות מחיר מרכזיות" : "KEY PRICE LEVELS"}</p>
            <div className="relative">
              {/* Resistance levels */}
              {(ta.resistance_levels ?? []).slice(0, 3).map((r) => (
                <div key={r} className="flex items-center gap-2 mb-1.5">
                  <div className="w-16 text-right">
                    <span className="text-xs text-red-400 font-bold">${r.toFixed(2)}</span>
                  </div>
                  <div className="flex-1 h-px bg-red-800/60 relative">
                    <span className="absolute right-0 -top-2.5 text-xs text-red-600">R</span>
                  </div>
                </div>
              ))}

              {/* Current price */}
              {ta.current_price && (
                <div className="flex items-center gap-2 my-2">
                  <div className="w-16 text-right">
                    <span className="text-xs text-white font-bold">${ta.current_price.toFixed(2)}</span>
                  </div>
                  <div className="flex-1 h-0.5 bg-white/30 relative">
                    <span className="absolute right-0 -top-2.5 text-xs text-gray-400">{isHe ? "כעת" : "NOW"}</span>
                  </div>
                </div>
              )}

              {/* Support levels */}
              {(ta.support_levels ?? []).slice(0, 3).map((s) => (
                <div key={s} className="flex items-center gap-2 mb-1.5">
                  <div className="w-16 text-right">
                    <span className="text-xs text-green-400 font-bold">${s.toFixed(2)}</span>
                  </div>
                  <div className="flex-1 h-px bg-green-800/60 relative">
                    <span className="absolute right-0 -top-2.5 text-xs text-green-600">S</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Row 4: Chart patterns */}
        {ta.chart_patterns && ta.chart_patterns.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {ta.chart_patterns.map((p) => (
              <span key={p} className={`text-xs px-2 py-1 rounded font-bold tracking-wider border ${
                p.includes("UP") || p.includes("LOW") || p.includes("GOLDEN")
                  ? "bg-green-950/40 text-green-400 border-green-800/40"
                  : p.includes("DOWN") || p.includes("HIGH") || p.includes("DEATH")
                  ? "bg-red-950/40 text-red-400 border-red-800/40"
                  : "bg-gray-800 text-gray-400 border-gray-700"
              }`}>
                {p.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        )}

        {/* Row 5: Signal reasoning */}
        {ta.signal_reasoning && !hasError && (
          <div className="border-t border-gray-800 pt-4">
            <p className="text-xs text-gray-600 mb-1">SIGNAL REASONING</p>
            <p className="text-xs text-gray-400 leading-relaxed">{ta.signal_reasoning}</p>
          </div>
        )}

        {/* Entry / Stop suggestion row */}
        {(ta.entry_price || rec.stop_loss) && !hasError && (
          <div className="grid grid-cols-2 gap-3 border-t border-gray-800 pt-4">
            {ta.entry_price && (
              <div>
                <p className="text-xs text-gray-600">ENTRY ZONE</p>
                <p className="text-sm font-bold text-blue-400">${ta.entry_price.toFixed(2)}</p>
              </div>
            )}
            {rec.stop_loss && (
              <div>
                <p className="text-xs text-gray-600">STOP LOSS</p>
                <p className="text-sm font-bold text-red-400">${rec.stop_loss.toFixed(2)}</p>
              </div>
            )}
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
