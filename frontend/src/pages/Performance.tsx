import React, { useEffect, useState } from "react";
import { useT } from "../i18n/t";
import { useAppSelector } from "../store";
import { performanceApi } from "../api/client";
import PerformanceComparisonChart from "../components/Charts/PerformanceComparisonChart";
import PerformanceTimelineChart from "../components/Charts/PerformanceTimelineChart";
import PortfolioHistoryChart from "../components/Charts/PortfolioHistoryChart";
import BacktestChart from "../components/Charts/BacktestChart";

const Performance: React.FC = () => {
  const t = useT();
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
      ? (t("WIN", "ניצחון"))
      : r === "LOSS"
      ? (t("LOSS", "הפסד"))
      : (t("NEUTRAL", "ניטרלי"));

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold print-header">
            {t("AI Performance Analytics", "ביצועי מערכת AI")}
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            {t("Objective comparison of AI recommendations vs the S&P 500", "השוואה אובייקטיבית בין ביצועי ההמלצות לבין S&P 500")}
          </p>
        </div>
        <button
          onClick={() => window.print()}
          className="no-print flex items-center gap-2 text-sm bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 hover:text-white rounded-xl px-4 py-2 transition-colors"
        >
          <span>📄</span>
          {t("Export PDF", "ייצוא PDF")}
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
              // Measured over calls that actually moved. A NEUTRAL is a stock
              // that went nowhere in thirty days, not a failed call, and
              // counting it as one printed 18.1% directly above "13W / 3L" —
              // a subtitle from which any reader computes 81%. The neutral
              // count is stated so the sample is not overstated either.
              label: t("Win Rate", "אחוז הצלחה"),
              value: `${summary.win_rate_pct}%`,
              sub: t("{w} wins / {l} losses · {n} flat", "{w} מוצלחות / {l} כושלות · {n} ללא שינוי",
                     { w: summary.win_count, l: summary.loss_count, n: summary.neutral_count }),
              color: summary.win_rate_pct >= 55 ? "text-green-400" : summary.win_rate_pct >= 45 ? "text-yellow-400" : "text-red-400",
            },
            {
              label: t("Avg Return", "תשואה ממוצעת"),
              value: `${summary.avg_return_pct > 0 ? "+" : ""}${summary.avg_return_pct}%`,
              sub: t("per trade", "לעסקה"),
              color: summary.avg_return_pct >= 0 ? "text-green-400" : "text-red-400",
            },
            {
              // Distinct from the cumulative alpha on the chart below, which
              // compounds a portfolio over time. Both were labelled "Alpha vs
              // S&P 500" and showed opposite signs on the same screen.
              label: t("Excess return per trade", "עודף תשואה לעסקה"),
              value: `${summary.avg_vs_market_pct > 0 ? "+" : ""}${summary.avg_vs_market_pct}%`,
              sub: t("avg vs S&P 500", "ממוצע מול S&P 500"),
              color: summary.avg_vs_market_pct >= 0 ? "text-green-400" : "text-red-400",
            },
            {
              label: t("Tracked", "סה\"כ במעקב"),
              value: summary.total_tracked,
              sub: t("recommendations", "המלצות"),
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
          {t("No performance data yet. Updates 30 days after first approved recommendation.", "טרם נאספו נתוני ביצועים. יתעדכן לאחר 30 יום מאישור ההמלצה הראשונה.")}
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
            { label: t("Best Trade", "העסקה הטובה ביותר"), trade: summary.best_trade, color: "green" },
            { label: t("Worst Trade", "העסקה הגרועה ביותר"), trade: summary.worst_trade, color: "red" },
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
            <h2 className="font-bold">{t("Recent Outcomes", "תוצאות אחרונות")}</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-gray-500 text-xs">
                  <th className="text-start px-5 py-3">{t("Symbol", "סימבול")}</th>
                  <th className="text-start px-4 py-3">{t("Type", "סוג")}</th>
                  <th className="text-start px-4 py-3">{t("Entry", "כניסה")}</th>
                  <th className="text-start px-4 py-3">{t("Exit", "יציאה")}</th>
                  <th className="text-start px-4 py-3">{t("Return", "תשואה")}</th>
                  <th className="text-start px-4 py-3">{t("vs Market", "vs שוק")}</th>
                  <th className="text-start px-4 py-3">{t("Result", "תוצאה")}</th>
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
