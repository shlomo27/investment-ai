/**
 * The answer, before the evidence.
 *
 * The report opened straight into analysis, so the reader had to assemble the
 * conclusion themselves out of several screens of prose. This states it first
 * — what the call is, at what prices, and how much to risk — and leaves the
 * reasoning to the sections below for anyone who wants it.
 *
 * It deliberately does NOT repeat the hero card above it. Rendering entry,
 * target, stop and confidence a second time added a whole screen of
 * duplication before the reader reached any content — which is the problem
 * this was meant to solve, not a way to solve it. What it adds is what the
 * hero does not say: the one-sentence why, the risk/reward ratio, and how
 * much of it to hold.
 */
import React from "react";
import { Recommendation } from "../../types";

type Props = { rec: Recommendation; isHe: boolean };

const ACTION: Record<string, { he: string; en: string; cls: string }> = {
  STRONG_BUY: { he: "קנייה חזקה", en: "Strong buy", cls: "text-green-400" },
  BUY: { he: "קנייה", en: "Buy", cls: "text-green-400" },
  HOLD: { he: "החזקה", en: "Hold", cls: "text-yellow-400" },
  SELL: { he: "מכירה", en: "Sell", cls: "text-red-400" },
  STRONG_SELL: { he: "מכירה חזקה", en: "Strong sell", cls: "text-red-400" },
};

const BottomLine: React.FC<Props> = ({ rec, isHe }) => {
  const action = ACTION[rec.recommendation_type] ?? {
    he: rec.recommendation_type,
    en: rec.recommendation_type,
    cls: "text-gray-300",
  };

  const entry = rec.current_price_at_recommendation;
  const risk = entry && rec.stop_loss ? Math.abs(entry - rec.stop_loss) : null;
  const reward = entry && rec.target_price ? Math.abs(rec.target_price - entry) : null;
  const rr = risk && reward && risk > 0 ? reward / risk : null;

  const fa = rec.fundamental_analysis;
  // The thesis is the one-sentence "why". Fall back through what exists
  // rather than showing an empty box.
  const why = fa?.thesis || rec.fundamental_notes || rec.senior_review_notes || "";

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-2xl p-5 space-y-4">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <div className="flex items-baseline gap-2">
          <span className="text-[11px] text-gray-500">
            {isHe ? "השורה התחתונה" : "Bottom line"}
          </span>
          <span className={`text-lg font-bold ${action.cls}`}>
            {isHe ? action.he : action.en}
          </span>
        </div>
        {/* R/R is the one headline figure the hero card does not carry. */}
        {rr && (
          <span className="text-xs text-gray-500">
            {isHe ? "סיכוי מול סיכון" : "Risk / reward"}{" "}
            <span
              className={`font-semibold font-mono ${
                rr >= 2 ? "text-green-400" : "text-gray-300"
              }`}
            >
              1 : {rr.toFixed(1)}
            </span>
          </span>
        )}
      </div>

      {why && (
        <p className="text-sm text-gray-300 leading-relaxed">{why}</p>
      )}

      {/* Allocation is the part people skip and should not: it is the
          committee saying how much of this to hold, not whether to. */}
      {fa?.allocation_recommendation && (
        <p className="text-xs text-gray-500">
          {isHe ? "הקצאה מומלצת: " : "Suggested allocation: "}
          <span className="text-gray-300">
            {fa.allocation_recommendation}
            {fa.suggested_weight_range ? ` · ${fa.suggested_weight_range}` : ""}
          </span>
        </p>
      )}
    </div>
  );
};

export default BottomLine;
