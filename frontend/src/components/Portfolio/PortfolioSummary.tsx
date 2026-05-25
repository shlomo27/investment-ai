import React from "react";
import { PortfolioSummary as PortfolioSummaryType } from "../../types";

interface Props {
  summary: PortfolioSummaryType;
  isHe?: boolean;
}

const PortfolioSummary: React.FC<Props> = ({ summary, isHe = false }) => {
  const fmt = (v: number) =>
    `₪${Math.abs(v).toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const pnlPositive = summary.total_pnl >= 0;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
        <p className="text-xs text-gray-400 mb-1">{isHe ? "שווי כולל" : "Total Value"}</p>
        <p className="text-xl font-bold">{fmt(summary.total_value)}</p>
      </div>
      <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
        <p className="text-xs text-gray-400 mb-1">{isHe ? "מזומן" : "Cash"}</p>
        <p className="text-xl font-bold text-green-400">{fmt(summary.cash_balance)}</p>
      </div>
      <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
        <p className="text-xs text-gray-400 mb-1">{isHe ? "רווח/הפסד" : "P&L"}</p>
        <p className={`text-xl font-bold ${pnlPositive ? "text-green-400" : "text-red-400"}`}>
          {pnlPositive ? "+" : ""}{fmt(summary.total_pnl)}
        </p>
        <p className={`text-xs ${pnlPositive ? "text-green-400" : "text-red-400"}`}>
          {pnlPositive ? "+" : ""}{summary.total_pnl_pct.toFixed(2)}%
        </p>
      </div>
      <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
        <p className="text-xs text-gray-400 mb-1">{isHe ? "עמדות" : "Positions"}</p>
        <p className="text-xl font-bold text-blue-400">{summary.position_count}</p>
      </div>
    </div>
  );
};

export default PortfolioSummary;
