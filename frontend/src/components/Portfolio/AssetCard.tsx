import React from "react";
import { PortfolioPosition } from "../../types";

interface Props {
  position: PortfolioPosition;
  isHe?: boolean;
}

const AssetCard: React.FC<Props> = ({ position: pos, isHe = false }) => {
  const fmt = (v: number) =>
    `₪${Math.abs(v).toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const pnlPos = pos.pnl >= 0;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 flex items-center justify-between hover:border-gray-700 transition-colors">
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 bg-blue-600/20 rounded-xl flex items-center justify-center">
          <span className="font-bold text-sm text-blue-400">{pos.symbol.slice(0, 2)}</span>
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
      </div>
    </div>
  );
};

export default AssetCard;
