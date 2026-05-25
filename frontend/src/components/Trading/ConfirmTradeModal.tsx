import React, { useState, useEffect } from "react";
import { Recommendation, OrderType } from "../../types";
import { ordersApi } from "../../api/client";

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

  const price = rec.current_price_at_recommendation || 0;
  const total = quantity * price;
  const isBuy = orderType === OrderType.BUY;

  useEffect(() => {
    if (!isBuy || !price || quantity <= 0) return;
    const timer = setTimeout(async () => {
      try {
        const check = await ordersApi.checkExposure(rec.symbol, total);
        if (check.blocked) {
          setExposureBlocked(true);
          setExposureWarning(check.message);
        } else if (check.warning) {
          setExposureBlocked(false);
          setExposureWarning(check.message);
        } else {
          setExposureBlocked(false);
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
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold">
            {isHe ? "אישור עסקה" : "Confirm Trade"}
          </h2>
          <button onClick={onCancel} className="text-gray-400 hover:text-white">✕</button>
        </div>

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
                ₪{rec.target_price.toLocaleString("en", { minimumFractionDigits: 2 })}
              </span>
            </div>
          )}
          {rec.stop_loss && (
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">{isHe ? "סטופ לוס" : "Stop Loss"}</span>
              <span className="font-bold text-red-400">
                ₪{rec.stop_loss.toLocaleString("en", { minimumFractionDigits: 2 })}
              </span>
            </div>
          )}
        </div>

        {/* Quantity Input */}
        <div className="mb-4">
          <label className="block text-sm text-gray-400 mb-2">
            {isHe ? "כמות" : "Quantity"}
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
          <span className="font-bold">{isHe ? "סה\"כ" : "Total Amount"}</span>
          <span className={`text-xl font-bold ${isBuy ? "text-green-400" : "text-red-400"}`}>
            ₪{total.toLocaleString("en", { minimumFractionDigits: 2 })}
          </span>
        </div>

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
              ? (isHe ? "מבצע..." : "Processing...")
              : isBuy
              ? (isHe ? "אישור רכישה" : "Confirm Buy")
              : (isHe ? "אישור מכירה" : "Confirm Sell")}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmTradeModal;
