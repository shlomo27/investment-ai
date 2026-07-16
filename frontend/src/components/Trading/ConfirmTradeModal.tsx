import React, { useState, useEffect } from "react";
import { Recommendation, OrderType } from "../../types";
import { ordersApi, portfolioApi } from "../../api/client";

interface Props {
  recommendation: Recommendation;
  orderType: OrderType;
  isHe: boolean;
  onConfirm: (quantity: number, price: number) => Promise<void>;
  onCancel: () => void;
}

const ConfirmTradeModal: React.FC<Props> = ({
  recommendation: rec,
  orderType,
  isHe,
  onConfirm,
  onCancel,
}) => {
  const [quantity, setQuantity] = useState<number>(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [exposureWarning, setExposureWarning] = useState<string | null>(null);
  const [exposureBlocked, setExposureBlocked] = useState(false);
  const [existingQty, setExistingQty] = useState<number | null>(null);
  const [existingAvg, setExistingAvg] = useState<number | null>(null);

  const price = rec.current_price_at_recommendation || 0;
  const cur = rec.symbol.endsWith(".TA") ? "₪" : "$";

  // On open, check whether this symbol is ALREADY in the tracking portfolio,
  // so we can warn before the user records a second (duplicate) holding.
  useEffect(() => {
    let cancelled = false;
    portfolioApi.getSummary()
      .then((s) => {
        if (cancelled) return;
        const pos = s.positions?.find((p) => p.symbol === rec.symbol && p.quantity > 0);
        setExistingQty(pos ? pos.quantity : 0);
        setExistingAvg(pos ? pos.avg_buy_price : null);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [rec.symbol]);
  const total = quantity * price;
  const isBuy = orderType === OrderType.BUY;

  useEffect(() => {
    if (!isBuy || !price || quantity <= 0) return;
    const timer = setTimeout(async () => {
      try {
        const check = await ordersApi.checkExposure(rec.symbol, total);
        // Advisory only — the trade already happened at the broker; we never
        // refuse to RECORD a real position, we just inform about concentration.
        setExposureBlocked(false);
        if (check.blocked || check.warning) {
          const pct = check.current_exposure_pct?.toFixed(1);
          const max = check.max_allowed_pct?.toFixed(0);
          setExposureWarning(
            pct && max
              ? `שים לב: ההחזקה תהווה ${pct}% מתיק המעקב — מעל הרף המומלץ (${max}%). נרשם כרגיל.`
              : check.message
          );
        } else {
          setExposureWarning(null);
        }
      } catch (e) {
        // ignore
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [quantity, total, isBuy]);

  const handleConfirm = async () => {
    setIsSubmitting(true);
    try {
      await onConfirm(quantity, price);
    } catch (e) {
      // handled by parent
    }
    setIsSubmitting(false);
  };

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50"
      onClick={onCancel}
    >
      <div
        className="bg-gray-900 rounded-2xl p-6 w-full max-w-md border border-gray-700"
        onClick={(e) => e.stopPropagation()}
        dir={isHe ? "rtl" : "ltr"}
      >
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xl font-bold">
            {isHe
              ? (isBuy ? "עדכון תיק — סימון החזקה" : "עדכון תיק — סימון מכירה")
              : (isBuy ? "Portfolio Update — Add Holding" : "Portfolio Update — Record Sale")}
          </h2>
          <button onClick={onCancel} className="text-gray-400 hover:text-white">✕</button>
        </div>

        {/* Advisory-only clarification */}
        <p className="text-xs text-gray-500 mb-4 leading-relaxed">
          {isHe
            ? "המערכת אינה מבצעת מסחר. את הפעולה עצמה בצע אצל הברוקר שלך — וכאן סמן אותה, כדי שהמערכת תעקוב אחרי הפוזיציה ותשלח לך התראות (סיגנלים, חדשות, סטופ-לוס)."
            : "This system does not execute trades. Trade with your broker, then record it here so the system can monitor the position and alert you (signals, news, stop-loss)."}
        </p>

        {/* Trade Summary */}
        <div className={`p-4 rounded-xl mb-4 ${isBuy ? "bg-green-900/20 border border-green-700/50" : "bg-red-900/20 border border-red-700/50"}`}>
          <div className="flex items-center gap-3 mb-3">
            <span className="text-2xl font-bold">{rec.symbol}</span>
            <span className={`text-sm font-bold px-2 py-0.5 rounded ${isBuy ? "bg-green-800 text-green-300" : "bg-red-800 text-red-300"}`}>
              {orderType}
            </span>
          </div>
          {rec.asset_name && (
            <p className="text-sm text-gray-400">{rec.asset_name}</p>
          )}
        </div>

        {/* AI Recommendation Context */}
        <div className="bg-gray-800 rounded-xl p-4 mb-4">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-gray-400">{isHe ? "המלצת AI" : "AI Recommendation"}</span>
            <span className="font-bold">{rec.recommendation_type}</span>
          </div>
          <div className="flex justify-between text-sm mb-2">
            <span className="text-gray-400">{isHe ? "ביטחון" : "Confidence"}</span>
            <span className="font-bold">{rec.confidence_score.toFixed(0)}%</span>
          </div>
          {rec.target_price && (
            <div className="flex justify-between text-sm mb-2">
              <span className="text-gray-400">{isHe ? "יעד מחיר" : "Target Price"}</span>
              <span className="font-bold text-green-400">
                {cur}{rec.target_price.toLocaleString("en", { minimumFractionDigits: 2 })}
              </span>
            </div>
          )}
          {rec.stop_loss && (
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">{isHe ? "סטופ לוס" : "Stop Loss"}</span>
              <span className="font-bold text-red-400">
                {cur}{rec.stop_loss.toLocaleString("en", { minimumFractionDigits: 2 })}
              </span>
            </div>
          )}
        </div>

        {/* Quantity Input */}
        <div className="mb-4">
          <label className="block text-sm text-gray-400 mb-2">
            {isHe
              ? (isBuy ? "כמה יחידות רכשת אצל הברוקר?" : "כמה יחידות מכרת?")
              : (isBuy ? "How many units did you buy at your broker?" : "How many units did you sell?")}
          </label>
          <input
            type="number"
            value={quantity}
            onChange={(e) => setQuantity(Math.max(0.0001, Number(e.target.value)))}
            min={0.0001}
            step={1}
            className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-xl font-bold text-white focus:outline-none focus:border-blue-500"
          />
        </div>

        {/* Total */}
        <div className="flex justify-between py-3 border-t border-b border-gray-800 mb-4">
          <span className="font-bold">{isHe ? "שווי ההחזקה" : "Position Value"}</span>
          <span className={`text-xl font-bold ${isBuy ? "text-green-400" : "text-red-400"}`}>
            {cur}{total.toLocaleString("en", { minimumFractionDigits: 2 })}
          </span>
        </div>

        {/* Already-held warning — prevents an accidental duplicate holding */}
        {isBuy && existingQty !== null && existingQty > 0 && (
          <div className="rounded-xl p-3 mb-4 text-sm bg-blue-900/20 border border-blue-700 text-blue-300">
            ℹ️ {isHe
              ? `אתה כבר מחזיק ${existingQty.toLocaleString("en")} יחידות של ${rec.symbol}${existingAvg ? ` (מחיר ממוצע ${cur}${existingAvg.toFixed(2)})` : ""}. ההוספה תצטרף לפוזיציה הקיימת — לא תיווצר החזקה נפרדת. אם זו טעות, לחץ ביטול.`
              : `You already hold ${existingQty.toLocaleString("en")} units of ${rec.symbol}${existingAvg ? ` (avg ${cur}${existingAvg.toFixed(2)})` : ""}. This will add to your existing position, not create a separate one. Cancel if this is a mistake.`}
          </div>
        )}

        {/* Exposure Warning */}
        {exposureWarning && (
          <div className={`rounded-xl p-3 mb-4 text-sm ${exposureBlocked ? "bg-red-900/20 border border-red-700 text-red-400" : "bg-yellow-900/20 border border-yellow-700 text-yellow-400"}`}>
            {exposureBlocked ? "🚫" : "⚠️"} {exposureWarning}
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 border border-gray-700 rounded-xl py-3 text-gray-400 hover:text-white hover:border-gray-600"
          >
            {isHe ? "ביטול" : "Cancel"}
          </button>
          <button
            onClick={handleConfirm}
            disabled={isSubmitting || exposureBlocked || quantity <= 0}
            className={`flex-1 rounded-xl py-3 font-bold transition-colors disabled:opacity-50 ${
              isBuy
                ? "bg-green-600 hover:bg-green-700 text-white"
                : "bg-red-600 hover:bg-red-700 text-white"
            }`}
          >
            {isSubmitting
              ? (isHe ? "מעדכן..." : "Updating...")
              : isBuy
              ? (existingQty && existingQty > 0
                  ? (isHe ? "הוסף לפוזיציה הקיימת" : "Add to Existing Position")
                  : (isHe ? "הוסף לתיק המעקב" : "Add to Tracked Portfolio"))
              : (isHe ? "עדכן מכירה בתיק" : "Record Sale in Portfolio")}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmTradeModal;
