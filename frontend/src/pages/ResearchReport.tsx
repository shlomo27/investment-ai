import React, { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useAppSelector } from "../store";
import { recommendationsApi, ordersApi } from "../api/client";
import { Recommendation, RecommendationType, OrderType } from "../types";
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
  const bias = fa?.direction_bias || "NEUTRAL";
  const isShort = rec.recommendation_type === RecommendationType.SELL || rec.recommendation_type === RecommendationType.STRONG_SELL;
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

      {/* Technical Analysis */}
      {rec.technical_analysis && (
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <h2 className="font-bold mb-4">{isHe ? "ניתוח טכני" : "Technical Analysis"}</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            {rec.technical_analysis.rsi_14 != null && (
              <div>
                <p className="text-xs text-gray-500">RSI 14</p>
                <p className={`text-lg font-bold ${
                  rec.technical_analysis.rsi_14 > 70 ? "text-red-400" :
                  rec.technical_analysis.rsi_14 < 30 ? "text-green-400" : "text-white"
                }`}>
                  {rec.technical_analysis.rsi_14.toFixed(1)}
                </p>
              </div>
            )}
            <div>
              <p className="text-xs text-gray-500">{isHe ? "סיגנל" : "Signal"}</p>
              <p className={`text-sm font-bold ${
                rec.technical_analysis.timing_signal?.includes("BUY") ? "text-green-400" :
                rec.technical_analysis.timing_signal?.includes("SELL") ? "text-red-400" : "text-yellow-400"
              }`}>
                {rec.technical_analysis.timing_signal}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">{isHe ? "ציון טכני" : "Tech Score"}</p>
              <p className="text-lg font-bold">{rec.technical_analysis.technical_score?.toFixed(0)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">{isHe ? "עוצמה" : "Strength"}</p>
              <p className="text-sm font-bold text-gray-300">{rec.technical_analysis.signal_strength}</p>
            </div>
          </div>
          {rec.technical_analysis.signal_reasoning && (
            <p className="text-sm text-gray-300">{rec.technical_analysis.signal_reasoning}</p>
          )}
        </div>
      )}

      {!rec.technical_analysis && (
        <div className="text-center py-4">
          <button
            onClick={handleRequestTechnical}
            disabled={technicalLoading}
            className="text-sm text-blue-400 hover:text-blue-300 disabled:text-gray-600"
          >
            {technicalLoading ? (isHe ? "מבצע ניתוח טכני..." : "Running technical analysis...") : (isHe ? "הוסף ניתוח טכני" : "Add Technical Analysis")}
          </button>
        </div>
      )}

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
