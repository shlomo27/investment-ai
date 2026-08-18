import React, { useState } from "react";
import { PortfolioPosition } from "../../types";

interface Props {
  position: PortfolioPosition;
  isHe?: boolean;
  onRemove?: (symbol: string) => Promise<void>;
}

const AssetCard: React.FC<Props> = ({ position: pos, isHe = false, onRemove }) => {
  // TASE prices are in ₪, US-listed stocks in $
  const cur = pos.symbol.endsWith(".TA") ? "₪" : "$";
  const fmt = (v: number) =>
    `${cur}${Math.abs(v).toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const [confirming, setConfirming] = useState(false);
  const [removing, setRemoving] = useState(false);

  const handleRemove = async () => {
    if (!onRemove) return;
    setRemoving(true);
    try {
      await onRemove(pos.symbol);
    } finally {
      setRemoving(false);
      setConfirming(false);
    }
  };

  const pnlPos = pos.pnl >= 0;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 flex items-center justify-between hover:border-gray-700 transition-colors">
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 bg-blue-600/20 rounded-xl flex items-center justify-center">
          <span className="font-bold text-sm text-blue-400">{pos.symbol.replace(".TA", "").slice(0, 3)}</span>
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="font-bold">{pos.symbol}</span>
            {pos.asset_name && <span className="text-xs text-gray-400">{pos.asset_name}</span>}
          </div>
          <div className="flex gap-3 text-xs text-gray-400 mt-0.5">
            <span>{pos.quantity.toFixed(4)} {isHe ? "יח'" : "units"}</span>
            <span>{isHe ? "מחיר ממוצע:" : "Avg:"} {fmt(pos.avg_buy_price)}</span>
          </div>
        </div>
      </div>

      <div className="text-right">
        <p className="font-bold">{fmt(pos.current_value)}</p>
        <div className="flex items-center justify-end gap-2 mt-0.5">
          <span className={`text-xs font-medium ${pnlPos ? "text-green-400" : "text-red-400"}`}>
            {pnlPos ? "+" : ""}{fmt(pos.pnl)} ({pnlPos ? "+" : ""}{pos.pnl_percentage.toFixed(2)}%)
          </span>
        </div>
        <p className="text-xs text-gray-500 mt-0.5">
          {isHe ? "חשיפה:" : "Exposure:"} {pos.exposure_percentage.toFixed(1)}%
        </p>
        {onRemove && (
          confirming ? (
            <div className="flex items-center gap-2 justify-end mt-1.5">
              <button
                onClick={handleRemove}
                disabled={removing}
                className="text-xs bg-red-700 hover:bg-red-600 disabled:opacity-60 text-white px-2 py-1 rounded"
              >
                {removing ? "..." : (isHe ? "אשר הסרה" : "Confirm")}
              </button>
              <button
                onClick={() => setConfirming(false)}
                className="text-xs text-gray-400 hover:text-white px-2 py-1"
              >
                {isHe ? "ביטול" : "Cancel"}
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirming(true)}
              className="mt-2 text-xs border border-gray-700 text-gray-300 hover:text-red-300 hover:border-red-800/60 hover:bg-red-900/20 px-2.5 py-1 rounded-lg transition-colors"
              title={isHe ? "מכרת או סימנת בטעות? הסר מהתיק והתרעות ייפסקו" : "Sold or added by mistake? Remove and alerts stop"}
            >
              🗑 {isHe ? "הסר מהתיק" : "Remove"}
            </button>
          )
        )}
      </div>
    </div>
  );
};

export default AssetCard;
