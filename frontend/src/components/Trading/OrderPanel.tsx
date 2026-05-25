import React, { useState } from "react";
import { OrderType, ExposureCheck } from "../../types";
import { ordersApi } from "../../api/client";

interface Props {
  symbol: string;
  currentPrice: number;
  isHe?: boolean;
  onOrderPlaced?: () => void;
}

const OrderPanel: React.FC<Props> = ({ symbol, currentPrice, isHe = false, onOrderPlaced }) => {
  const [orderType, setOrderType] = useState<OrderType>(OrderType.BUY);
  const [quantity, setQuantity] = useState<number>(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [exposureCheck, setExposureCheck] = useState<ExposureCheck | null>(null);

  const totalAmount = quantity * currentPrice;

  const handleExposureCheck = async () => {
    if (orderType !== OrderType.BUY) {
      setExposureCheck(null);
      return;
    }
    try {
      const check = await ordersApi.checkExposure(symbol, totalAmount);
      setExposureCheck(check);
    } catch (e) {
      // ignore
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await ordersApi.createOrder({
        symbol,
        order_type: orderType,
        quantity,
        price: currentPrice,
      });
      setSuccess(true);
      onOrderPlaced?.();
      setTimeout(() => setSuccess(false), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Order failed");
    }
    setIsSubmitting(false);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="flex bg-gray-800 rounded-xl p-1">
        <button
          type="button"
          onClick={() => setOrderType(OrderType.BUY)}
          className={`flex-1 py-2 rounded-lg text-sm font-medium ${orderType === OrderType.BUY ? "bg-green-600 text-white" : "text-gray-400"}`}
        >
          {isHe ? "קנייה" : "Buy"}
        </button>
        <button
          type="button"
          onClick={() => setOrderType(OrderType.SELL)}
          className={`flex-1 py-2 rounded-lg text-sm font-medium ${orderType === OrderType.SELL ? "bg-red-600 text-white" : "text-gray-400"}`}
        >
          {isHe ? "מכירה" : "Sell"}
        </button>
      </div>

      <div>
        <label className="block text-sm text-gray-400 mb-1">{isHe ? "כמות" : "Quantity"}</label>
        <input
          type="number"
          value={quantity}
          onChange={(e) => setQuantity(Number(e.target.value))}
          onBlur={handleExposureCheck}
          min={0.0001}
          step={0.0001}
          className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
        />
      </div>

      <div className="flex justify-between text-sm py-2 border-t border-gray-800">
        <span className="text-gray-400">{isHe ? "מחיר" : "Price"}</span>
        <span className="font-bold">₪{currentPrice.toLocaleString("en", { minimumFractionDigits: 2 })}</span>
      </div>

      <div className="flex justify-between text-sm font-bold">
        <span>{isHe ? "סה\"כ" : "Total"}</span>
        <span className={orderType === OrderType.BUY ? "text-green-400" : "text-red-400"}>
          ₪{totalAmount.toLocaleString("en", { minimumFractionDigits: 2 })}
        </span>
      </div>

      {exposureCheck?.warning && (
        <div className="bg-yellow-900/20 border border-yellow-700/50 rounded-lg p-2 text-xs text-yellow-400">
          ⚠️ {exposureCheck.message}
        </div>
      )}

      {error && (
        <div className="bg-red-900/20 border border-red-700 rounded-lg p-2 text-xs text-red-400">
          {error}
        </div>
      )}

      {success && (
        <div className="bg-green-900/20 border border-green-700 rounded-lg p-2 text-xs text-green-400">
          {isHe ? "הזמנה בוצעה בהצלחה!" : "Order placed successfully!"}
        </div>
      )}

      <button
        type="submit"
        disabled={isSubmitting || exposureCheck?.blocked}
        className={`w-full py-3 rounded-xl font-medium transition-colors disabled:opacity-50 ${
          orderType === OrderType.BUY
            ? "bg-green-600 hover:bg-green-700 text-white"
            : "bg-red-600 hover:bg-red-700 text-white"
        }`}
      >
        {isSubmitting
          ? (isHe ? "מבצע..." : "Submitting...")
          : orderType === OrderType.BUY
          ? (isHe ? "קנה" : "Buy")
          : (isHe ? "מכור" : "Sell")}
      </button>
    </form>
  );
};

export default OrderPanel;
