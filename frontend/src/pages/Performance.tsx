import React, { useEffect, useState } from "react";
import { useAppSelector } from "../store";
import { performanceApi } from "../api/client";
import PerformanceComparisonChart from "../components/Charts/PerformanceComparisonChart";
import PerformanceTimelineChart from "../components/Charts/PerformanceTimelineChart";
import PortfolioHistoryChart from "../components/Charts/PortfolioHistoryChart";
import BacktestChart from "../components/Charts/BacktestChart";

const Performance: React.FC = () => {
  const { user } = useAppSelector((s) => s.auth);
  const isHe = user?.preferred_language === "he";

  const [summary, setSummary] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(true);

  useEffect(() => {
    performanceApi.getSummary()
      .then(setSummary)
      .finally(() => setLoadingSummary(false));
    performanceApi.getHistory(20, true)
      .then(setHistory)
      .finally(() => setLoadingHistory(false));
  }, []);

  const resultColor = (r: string) =>
    r === "WIN" ? "text-green-400" : r === "LOSS" ? "text-red-400" : "text-yellow-400";

  const resultLabel = (r: string) =>
    r === "WIN"
      ? (isHe ? "ניצחון" : "WIN")
      : r === "LOSS"
      ? (isHe ? "הפסד" : "LOSS")
      : (isHe ? "ניטרלי" : "NEUTRAL");

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold print-header">
            {isHe ? "ביצועי מערכת AI" : "AI Performance Analytics"}
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            {isHe
              ? "השוואה אובייקטיבית בין ביצועי ההמלצות לבין S&P 500"
              : "Objective comparison of AI recommendations vs the S&P 500"}
          </p>
        </div>
        <button
          onClick={() => window.print()}
          className="no-print flex items-center gap-2 text-sm bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 hover:text-white rounded-xl px-4 py-2 transition-colors"
        >
          <span>📄</span>
          {isHe ? "ייצוא PDF" : "Export PDF"}
        </button>
      </div>

      {/* KPI Summary */}
      {loadingSummary ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 bg-gray-900 rounded-2xl animate-pulse border border-gray-800" />
          ))}
        </div>
      ) : summary && summary.total_tracked > 0 ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            {
              label: isHe ? "אחוז הצלחה" : "Win Rate",
              value: `${summary.win_rate_pct}%`,
              sub: `${summary.win_count}W / ${summary.loss_count}L`,
              color: summary.win_rate_pct >= 55 ? "text-green-400" : summary.win_rate_pct >= 45 ? "text-yellow-400" : "text-red-400",
            },
            {
              label: isHe ? "תשואה ממוצעת" : "Avg Return",
              value: `${summary.avg_return_pct > 0 ? "+" : ""}${summary.avg_return_pct}%`,
              sub: isHe ? "לעסקה" : "per trade",
              color: summary.avg_return_pct >= 0 ? "text-green-400" : "text-red-400",
            },
            {
              label: isHe ? "Alpha vs S&P 500" : "Alpha vs S&P",
              value: `${summary.avg_vs_market_pct > 0 ? "+" : ""}${summary.avg_vs_market_pct}%`,
              sub: isHe ? "מעל השוק" : "above market",
              color: summary.avg_vs_market_pct >= 0 ? "text-green-400" : "text-red-400",
            },
            {
              label: isHe ? "סה\"כ במעקב" : "Tracked",
              value: summary.total_tracked,
              sub: isHe ? "המלצות" : "recommendations",
              color: "text-white",
            },
          ].map((kpi) => (
            <div key={kpi.label} className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
              <p className="text-xs text-gray-500 mb-1">{kpi.label}</p>
              <p className={`text-2xl font-bold ${kpi.color}`}>{kpi.value}</p>
              <p className="text-xs text-gray-600 mt-1">{kpi.sub}</p>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 text-center text-gray-500">
          {isHe ? "טרם נאספו נתוני ביצועים. יתעדכן לאחר 30 יום מאישור ההמלצה הראשונה." : "No performance data yet. Updates 30 days after first approved recommendation."}
        </div>
      )}

      {/* S&P 500 Comparison Chart */}
      <PerformanceComparisonChart isHe={isHe} />

      {/* Monthly Timeline */}
      <PerformanceTimelineChart isHe={isHe} />

      {/* Backtest Simulation */}
      <BacktestChart isHe={isHe} />

      {/* Portfolio History */}
      <PortfolioHistoryChart isHe={isHe} days={90} />

      {/* Best / Worst Trade */}
      {summary?.best_trade && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[
            { label: isHe ? "העסקה הטובה ביותר" : "Best Trade", trade: summary.best_trade, color: "green" },
            { label: isHe ? "העסקה הגרועה ביותר" : "Worst Trade", trade: summary.worst_trade, color: "red" },
          ].map((item) => (
            <div key={item.label} className={`bg-gray-900 rounded-2xl p-5 border border-${item.color}-900/40`}>
              <p className="text-xs text-gray-500 mb-2">{item.label}</p>
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-bold text-lg">{item.trade.symbol}</p>
                  <p className="text-xs text-gray-400">{item.trade.type}</p>
                  <p className="text-xs text-gray-500 mt-1">
                    {item.trade.date ? new Date(item.trade.date).toLocaleDateString(isHe ? "he-IL" : "en-US") : ""}
                  </p>
                </div>
                <p className={`text-2xl font-bold text-${item.color}-400`}>
                  {item.trade.return_pct > 0 ? "+" : ""}{item.trade.return_pct?.toFixed(2)}%
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Recent Outcomes Table */}
      {history.length > 0 && (
        <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">
          <div className="p-5 border-b border-gray-800">
            <h2 className="font-bold">{isHe ? "תוצאות אחרונות" : "Recent Outcomes"}</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-gray-500 text-xs">
                  <th className="text-start px-5 py-3">{isHe ? "סימבול" : "Symbol"}</th>
                  <th className="text-start px-4 py-3">{isHe ? "סוג" : "Type"}</th>
                  <th className="text-start px-4 py-3">{isHe ? "כניסה" : "Entry"}</th>
                  <th className="text-start px-4 py-3">{isHe ? "יציאה" : "Exit"}</th>
                  <th className="text-start px-4 py-3">{isHe ? "תשואה" : "Return"}</th>
                  <th className="text-start px-4 py-3">{isHe ? "vs שוק" : "vs Market"}</th>
                  <th className="text-start px-4 py-3">{isHe ? "תוצאה" : "Result"}</th>
                </tr>
              </thead>
              <tbody>
                {history.map((r) => (
                  <tr key={r.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="px-5 py-3 font-bold">{r.symbol}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{r.type}</td>
                    <td className="px-4 py-3">
                      {r.entry_price ? `₪${r.entry_price.toFixed(2)}` : "—"}
                    </td>
                    <td className="px-4 py-3">
                      {r.outcome_price ? `₪${r.outcome_price.toFixed(2)}` : "—"}
                    </td>
                    <td className={`px-4 py-3 font-medium ${r.outcome_return_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {r.outcome_return_pct != null
                        ? `${r.outcome_return_pct > 0 ? "+" : ""}${r.outcome_return_pct.toFixed(2)}%`
                        : "—"}
                    </td>
                    <td className={`px-4 py-3 font-medium ${r.outcome_vs_market_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {r.outcome_vs_market_pct != null
                        ? `${r.outcome_vs_market_pct > 0 ? "+" : ""}${r.outcome_vs_market_pct.toFixed(2)}%`
                        : "—"}
                    </td>
                    <td className={`px-4 py-3 font-bold text-xs ${resultColor(r.outcome_result)}`}>
                      {resultLabel(r.outcome_result)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default Performance;
