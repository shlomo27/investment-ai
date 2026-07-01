import React, { useState } from "react";
import { Recommendation, RecommendationType, OrderType, TechnicalAnalysis } from "../../types";

interface Props {
  recommendation: Recommendation;
  isHe: boolean;
  technicalAnalysis?: TechnicalAnalysis;
  isLoadingTechnical: boolean;
  onRequestTechnical: () => void;
  onBuy: () => void;
  onSell: () => void;
  onDismiss: () => void;
}

const RecommendationCard: React.FC<Props> = ({
  recommendation: rec,
  isHe,
  technicalAnalysis: tech,
  isLoadingTechnical,
  onRequestTechnical,
  onBuy,
  onSell,
  onDismiss,
}) => {
  const [expanded, setExpanded] = useState(false);

  const isBuy = rec.recommendation_type.includes("BUY");
  const isSell = rec.recommendation_type.includes("SELL");

  const recColor = isBuy ? "text-green-400 border-green-700/50" : isSell ? "text-red-400 border-red-700/50" : "text-yellow-400 border-yellow-700/50";
  const recBg = isBuy ? "bg-green-900/10" : isSell ? "bg-red-900/10" : "bg-yellow-900/10";

  const fmt = (v?: number) =>
    v !== undefined ? `₪${v.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "N/A";

  return (
    <div className={`bg-gray-900 rounded-2xl border ${recColor} ${recBg} overflow-hidden`}>
      {/* Header */}
      <div className="p-5">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <span className="text-2xl font-bold">{rec.symbol}</span>
              <span className={`text-sm font-bold px-2 py-0.5 rounded ${isBuy ? "bg-green-800/50" : isSell ? "bg-red-800/50" : "bg-yellow-800/50"} ${recColor.split(" ")[0]}`}>
                {rec.recommendation_type}
              </span>
            </div>
            {rec.asset_name && <p className="text-sm text-gray-400">{rec.asset_name}</p>}
          </div>

          <div className="text-right space-y-1">
            <div className="text-2xl font-bold mb-1">
              {rec.confidence_score.toFixed(0)}%
            </div>
            <p className="text-xs text-gray-400">{isHe ? "ביטחון" : "Confidence"}</p>
            {(() => {
              const alloc = (rec.fundamental_analysis as any)?.allocation_recommendation;
              if (!alloc || alloc === "NONE") return null;
              const cls = alloc === "HIGH" ? "bg-green-900/40 text-green-300 border-green-700/40"
                : alloc === "MEDIUM" ? "bg-blue-900/40 text-blue-300 border-blue-700/40"
                : "bg-yellow-900/40 text-yellow-300 border-yellow-700/40";
              const label = isHe
                ? { HIGH: "הקצאה גבוהה", MEDIUM: "הקצאה בינונית", LOW: "הקצאה נמוכה" }[alloc] || alloc
                : alloc;
              return (
                <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded border ${cls}`}>
                  {label}
                </span>
              );
            })()}
          </div>
        </div>

        {/* Key Metrics */}
        <div className="grid grid-cols-3 gap-4 mt-4">
          <div>
            <p className="text-xs text-gray-400">{isHe ? "מחיר נוכחי" : "Current Price"}</p>
            <p className="font-bold">{fmt(rec.current_price_at_recommendation)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400">{isHe ? "יעד מחיר" : "Target"}</p>
            <p className="font-bold text-green-400">{fmt(rec.target_price)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400">{isHe ? "סטופ לוס" : "Stop Loss"}</p>
            <p className="font-bold text-red-400">{fmt(rec.stop_loss)}</p>
          </div>
        </div>

        {/* Senior Notes Preview */}
        {rec.senior_notes && !expanded && (
          <p className="mt-3 text-sm text-gray-300 line-clamp-2">
            {rec.senior_notes}
          </p>
        )}
      </div>

      {/* Expanded Content */}
      {expanded && (
        <div className="border-t border-gray-800 p-5 space-y-4">
          {/* Fundamental Analysis */}
          {rec.fundamental_analysis && (
            <div>
              <h4 className="text-sm font-bold mb-2 text-blue-400">
                {isHe ? "ניתוח בסיסי" : "Fundamental Analysis"}
              </h4>
              <div className="grid grid-cols-2 gap-3">
                {rec.fundamental_analysis.bull_case && (
                  <div className="bg-green-900/20 rounded-xl p-3">
                    <p className="text-xs text-green-400 font-medium mb-1">{isHe ? "תרחיש חיובי" : "Bull Case"}</p>
                    <p className="text-xs text-gray-300">{rec.fundamental_analysis.bull_case}</p>
                  </div>
                )}
                {rec.fundamental_analysis.bear_case && (
                  <div className="bg-red-900/20 rounded-xl p-3">
                    <p className="text-xs text-red-400 font-medium mb-1">{isHe ? "תרחיש שלילי" : "Bear Case"}</p>
                    <p className="text-xs text-gray-300">{rec.fundamental_analysis.bear_case}</p>
                  </div>
                )}
              </div>
              {rec.fundamental_analysis.risk_factors?.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-gray-400 mb-1">{isHe ? "גורמי סיכון" : "Risk Factors"}</p>
                  <ul className="space-y-1">
                    {rec.fundamental_analysis.risk_factors.map((r, i) => (
                      <li key={i} className="text-xs text-gray-300 flex items-start gap-1">
                        <span className="text-red-400 mt-0.5">•</span> {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Sentiment */}
          {rec.sentiment_data && (
            <div>
              <h4 className="text-sm font-bold mb-2 text-purple-400">
                {isHe ? "סנטימנט חברתי" : "Social Sentiment"}
              </h4>
              <div className="flex items-center gap-4">
                <div>
                  <p className="text-xs text-gray-400">{isHe ? "ציון" : "Score"}</p>
                  <p className={`font-bold ${rec.sentiment_data.score > 0 ? "text-green-400" : rec.sentiment_data.score < 0 ? "text-red-400" : "text-gray-400"}`}>
                    {rec.sentiment_data.score > 0 ? "+" : ""}{rec.sentiment_data.score.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">{isHe ? "אזכורים" : "Mentions"}</p>
                  <p className="font-bold">{rec.sentiment_data.mentions.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">{isHe ? "טרנד" : "Trending"}</p>
                  <p className={`font-bold ${rec.sentiment_data.trending ? "text-green-400" : "text-gray-400"}`}>
                    {rec.sentiment_data.trending ? "✓" : "—"}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Senior Notes */}
          {rec.senior_notes && (
            <div>
              <h4 className="text-sm font-bold mb-2 text-yellow-400">
                {isHe ? "ועדת בכירים" : "Senior Committee"}
              </h4>
              <p className="text-xs text-gray-300">{rec.senior_notes}</p>
            </div>
          )}

          {/* Technical Analysis */}
          {(tech || rec.technical_analysis) && (
            <div>
              <h4 className="text-sm font-bold mb-2 text-cyan-400">
                {isHe ? "ניתוח טכני" : "Technical Analysis"}
              </h4>
              {(() => {
                const t = tech || rec.technical_analysis;
                if (!t) return null;
                return (
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { label: "RSI", value: t.rsi_14?.toFixed(1) },
                      { label: "Signal", value: t.timing_signal },
                      { label: "Score", value: `${t.technical_score}/100` },
                    ].map((item) => (
                      <div key={item.label} className="bg-gray-800 rounded-lg p-2 text-center">
                        <p className="text-xs text-gray-400">{item.label}</p>
                        <p className="font-bold text-sm">{item.value || "N/A"}</p>
                      </div>
                    ))}
                  </div>
                );
              })()}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="px-5 pb-5 flex items-center gap-2">
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-gray-400 hover:text-white border border-gray-700 rounded-lg px-3 py-1.5"
        >
          {expanded ? (isHe ? "הסתר" : "Collapse") : (isHe ? "פרטים" : "Details")}
        </button>
        <button
          onClick={onRequestTechnical}
          disabled={isLoadingTechnical}
          className="text-xs bg-cyan-900/20 border border-cyan-700/50 text-cyan-400 rounded-lg px-3 py-1.5 hover:bg-cyan-900/40 disabled:opacity-50"
        >
          {isLoadingTechnical ? (isHe ? "מנתח..." : "Analyzing...") : (isHe ? "ניתוח טכני" : "Technical")}
        </button>
        <div className="flex-1" />
        {isBuy || (!isSell) ? (
          <button
            onClick={onBuy}
            className="bg-green-600 hover:bg-green-700 text-white rounded-lg px-4 py-1.5 text-sm font-medium"
          >
            {isHe ? "קנה" : "Buy"}
          </button>
        ) : null}
        {isSell && (
          <button
            onClick={onSell}
            className="bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-1.5 text-sm font-medium"
          >
            {isHe ? "מכור" : "Sell"}
          </button>
        )}
        <button
          onClick={onDismiss}
          className="text-gray-500 hover:text-gray-300 text-sm px-2"
        >
          ✕
        </button>
      </div>
    </div>
  );
};

export default RecommendationCard;
