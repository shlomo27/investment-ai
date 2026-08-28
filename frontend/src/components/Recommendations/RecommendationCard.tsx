import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { watchlistApi } from "../../api/client";
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
  suggestedAmount?: number; // legacy — no longer rendered
  suggestedPct?: number;
  approvedAt?: string;
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
  suggestedAmount,
  suggestedPct,
  approvedAt,
}) => {
  const [expanded, setExpanded] = useState(false);
  const [following, setFollowing] = useState(false);
  const [followMsg, setFollowMsg] = useState(false);
  const navigate = useNavigate();

  const handleFollowForEntry = async () => {
    setFollowing(true);
    try {
      await watchlistApi.addToWatchlist({
        symbol: rec.symbol,
        exchange: rec.symbol.endsWith(".TA") ? "TASE" : "NASDAQ",
        alert_on_technical_signal: true,
        notes: "Following for entry point",
      });
      setFollowMsg(true);
    } catch {
      // already on watchlist or failed — still show confirmation
      setFollowMsg(true);
    }
    setFollowing(false);
  };

  const isBuy = rec.recommendation_type.includes("BUY");
  const isSell = rec.recommendation_type.includes("SELL");

  const recColor = isBuy ? "text-green-400 border-green-700/50" : isSell ? "text-red-400 border-red-700/50" : "text-yellow-400 border-yellow-700/50";
  const recBg = isBuy ? "bg-green-900/10" : isSell ? "bg-red-900/10" : "bg-yellow-900/10";

  // TASE prices are shown in ₪, US-listed stocks in $
  const currency = rec.symbol.endsWith(".TA") ? "₪" : "$";
  const fmt = (v?: number) =>
    v !== undefined ? `${currency}${v.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "N/A";

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
            {(() => {
              // Entry readiness: combine the BUY thesis with the live technical
              // signal into one timing cue. Only for BUY recommendations.
              if (!isBuy) return null;
              const sig = (tech?.timing_signal || rec.technical_analysis?.timing_signal || "").toUpperCase();
              if (!sig) return null;
              if (sig === "BUY_NOW" || sig === "STRONG_BUY") {
                return <span className="inline-block mt-1 mr-1 text-xs px-2 py-0.5 rounded-full bg-green-900/50 text-green-300 border border-green-600/50">🟢 {isHe ? "נקודת כניסה טובה" : "Good entry"}</span>;
              }
              if (sig === "SELL_NOW" || sig === "STRONG_SELL" || sig === "WAIT") {
                return <span className="inline-block mt-1 mr-1 text-xs px-2 py-0.5 rounded-full bg-yellow-900/40 text-yellow-300 border border-yellow-700/40">🟡 {isHe ? "הזדמנות — המתן לייצוב" : "Wait for stabilization"}</span>;
              }
              return null;
            })()}
            {(() => {
              // Risk transparency: short positions and high-volatility stocks
              // carry materially different risk — always label them, whatever
              // the user's display filters are.
              const beta = typeof rec.beta === "number" ? rec.beta : null;
              // Volatility is stated on every card, not only the alarming ones.
              // Showing a badge exclusively for high-risk stocks meant a silent
              // card could mean "calm stock" or "never measured", and the
              // reader had no way to tell which.
              const band =
                beta === null ? null :
                beta < 0.8 ? {
                  label: isHe ? "תנודתיות נמוכה" : "Low volatility",
                  cls: "bg-green-950/60 text-green-300 border-green-800/50",
                  icon: "🛡️",
                } :
                beta < 1.3 ? {
                  label: isHe ? "תנודתיות רגילה" : "Market-like volatility",
                  cls: "bg-gray-800/80 text-gray-300 border-gray-700",
                  icon: "〰️",
                } :
                beta < 1.8 ? {
                  label: isHe ? "תנודתיות גבוהה" : "High volatility",
                  cls: "bg-orange-950/60 text-orange-300 border-orange-800/50",
                  icon: "⚡",
                } : {
                  label: isHe ? "תנודתיות גבוהה מאוד" : "Very high volatility",
                  cls: "bg-red-950/60 text-red-300 border-red-800/50",
                  icon: "⚡",
                };
              const betaHint = beta === null ? "" : isHe
                ? `בטא ${beta.toFixed(2)} — המניה זזה בערך פי ${beta.toFixed(2)} מהשוק. מודד תנועה מול השוק בלבד; מניה רגועה עדיין יכולה לקפוץ על חדשות שלה.`
                : `Beta ${beta.toFixed(2)} — moves about ${beta.toFixed(2)}× the market. Measures market-correlated movement only; a calm stock can still gap on its own news.`;
              if (!isSell && !band) return null;
              return (
                <>
                  {isSell && (
                    <span className="inline-block mt-1 mr-1 text-xs px-2 py-0.5 rounded-full bg-red-950/60 text-red-300 border border-red-800/50"
                          title={isHe ? "הימור על ירידת מחיר — הפסד אפשרי בלתי מוגבל" : "Betting on a decline — unlimited downside"}>
                      📉 {isHe ? "פוזיציית שורט" : "Short position"}
                    </span>
                  )}
                  {band && (
                    <span className={`inline-block mt-1 mr-1 text-xs px-2 py-0.5 rounded-full border ${band.cls}`}
                          title={betaHint}>
                      {band.icon} {band.label} · β {beta!.toFixed(2)}
                    </span>
                  )}
                </>
              );
            })()}
            {(() => {
              if (!approvedAt) return null;
              const ageDays = Math.floor((Date.now() - new Date(approvedAt).getTime()) / 86400000);
              // Thresholds follow the actual refresh policy. The weekly scan
              // only covers the current pre-screener pool, so a stock that left
              // the pool waits for its quarterly turn; the backend closes that
              // gap by re-queueing any live recommendation past 30 days and
              // retiring it at 45. The badge says which of those states this
              // card is in, so "old" no longer reads as "broken".
              if (ageDays < 7) {
                return <span className="inline-block mt-1 text-xs px-2 py-0.5 rounded-full bg-green-900/40 text-green-300 border border-green-700/40">🟢 {isHe ? "עדכנית" : "Fresh"}</span>;
              } else if (ageDays <= 30) {
                return <span className="inline-block mt-1 text-xs px-2 py-0.5 rounded-full bg-yellow-900/40 text-yellow-300 border border-yellow-700/40"
                             title={isHe ? "בתוך מחזור הריענון — הניתוח נבדק מחדש עד 30 יום" : "Within the refresh cycle — re-analysed within 30 days"}>🟡 {isHe ? `${ageDays} ימים` : `${ageDays} days`}</span>;
              } else {
                // Say what the reader should do, not what the system is doing.
                // "Awaiting re-check" is internal state: it tells someone
                // holding a 49-day-old card nothing about whether to act on it.
                return <span className="inline-block mt-1 text-xs px-2 py-0.5 rounded-full bg-orange-900/40 text-orange-300 border border-orange-700/40"
                             title={isHe
                               ? `יעד המחיר והסטופ נקבעו לפני ${ageDays} ימים, לפני שינויי מחיר ואולי לפני דוח רבעוני. המניה בתור לניתוח מחדש; אם לא תיבדק עד גיל 45 יום ההמלצה תוסר מהפיד. עד אז אל תפעל לפי המספרים האלה בלי לבדוק את המחיר הנוכחי.`
                               : `The target and stop were set ${ageDays} days ago, before subsequent price moves and possibly before an earnings report. It is queued for re-analysis and will be retired at 45 days if not re-checked. Until then do not act on these numbers without checking the current price.`}>🟠 {isHe ? `ניתוח בן ${ageDays} ימים — אמת מחיר לפני פעולה` : `${ageDays}-day-old analysis — verify price first`}</span>;
              }
            })()}
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
                ? ({ HIGH: "הקצאה גבוהה", MEDIUM: "הקצאה בינונית", LOW: "הקצאה נמוכה" } as Record<string, string>)[alloc] || alloc
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
        <div className="grid grid-cols-4 gap-4 mt-4">
          <div>
            {/* This is the price the analysis was written against, frozen at
                approval — not a live quote. Labelling it "current" told a
                reader looking at a two-week-old card that the stock trades
                there today, and the target percentage is measured from it. */}
            <p className="text-xs text-gray-400" title={isHe ? "המחיר שעליו נכתב הניתוח, לא מחיר השוק כרגע" : "The price the analysis was written against, not a live quote"}>
              {isHe ? "מחיר בעת ההמלצה" : "Price at recommendation"}
            </p>
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
          <div>
            {/* Risk/reward, computed from the committee's own target and stop.
                It is arithmetic, not an opinion, so unlike the confidence score
                it genuinely separates one recommendation from another: measured
                over a week of live signals, confidence spans 11 points with a
                standard deviation of 3, which cannot rank anything. */}
            {(() => {
              const entry = rec.current_price_at_recommendation;
              const target = rec.target_price;
              const stop = rec.stop_loss;
              if (!entry || !target || !stop) {
                return (
                  <>
                    <p className="text-xs text-gray-400">{isHe ? "סיכוי מול סיכון" : "Risk / reward"}</p>
                    <p className="font-bold text-gray-600">—</p>
                  </>
                );
              }
              const reward = Math.abs(target - entry);
              const risk = Math.abs(entry - stop);
              const ratio = risk > 0 ? reward / risk : null;
              const upPct = (reward / entry) * 100;
              const downPct = (risk / entry) * 100;
              const tone =
                ratio === null ? "text-gray-600"
                : ratio >= 2 ? "text-green-400"
                : ratio >= 1.5 ? "text-yellow-400"
                : "text-orange-400";
              return (
                <>
                  <p
                    className="text-xs text-gray-400"
                    title={isHe
                      ? `מסכנים ${downPct.toFixed(1)}% כדי להרוויח ${upPct.toFixed(1)}%`
                      : `Risking ${downPct.toFixed(1)}% to make ${upPct.toFixed(1)}%`}
                  >
                    {isHe ? "סיכוי מול סיכון" : "Risk / reward"}
                  </p>
                  <p className={`font-bold ${tone}`} dir="ltr">
                    {ratio === null ? "—" : `1 : ${ratio.toFixed(1)}`}
                  </p>
                </>
              );
            })()}
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
          onClick={() => navigate(`/technical/${rec.id}`)}
          className="text-xs bg-cyan-900/20 border border-cyan-700/50 text-cyan-400 rounded-lg px-3 py-1.5 hover:bg-cyan-900/40"
        >
          {isHe ? "ניתוח טכני" : "Technical"}
        </button>
        <button
          onClick={() => navigate(`/research/${rec.id}`)}
          className="text-xs bg-yellow-900/20 border border-yellow-700/50 text-yellow-400 rounded-lg px-3 py-1.5 hover:bg-yellow-900/40"
        >
          {isHe ? "מחקר מלא" : "Research"}
        </button>
        <div className="flex-1" />
        {(() => {
          if (!isBuy) return null;
          const sig = (tech?.timing_signal || rec.technical_analysis?.timing_signal || "").toUpperCase();
          const positive = sig === "BUY_NOW" || sig === "STRONG_BUY";
          if (positive) return null;  // already a good entry — no need to wait
          return followMsg ? (
            <span className="text-xs text-green-400 px-2">{isHe ? "✓ במעקב — נודיע בכניסה" : "✓ Following"}</span>
          ) : (
            <button
              onClick={handleFollowForEntry}
              disabled={following}
              className="text-xs bg-blue-900/20 border border-blue-700/50 text-blue-300 rounded-lg px-3 py-1.5 hover:bg-blue-900/40 disabled:opacity-60"
              title={isHe ? "נודיע לך כשהניתוח הטכני יאשר נקודת כניסה" : "We'll alert you when the technical confirms an entry point"}
            >
              {following ? "..." : (isHe ? "👁 עקוב לנקודת כניסה" : "👁 Follow for entry")}
            </button>
          );
        })()}
        {isBuy || (!isSell) ? (
          <button
            onClick={onBuy}
            className="bg-green-600 hover:bg-green-700 text-white rounded-lg px-4 py-1.5 text-sm font-medium"
          >
            {isHe ? "מחזיק? הוסף לתיק" : "Add to Portfolio"}
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
