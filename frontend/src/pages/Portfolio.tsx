import React, { useEffect, useState } from "react";
import { useAppDispatch, useAppSelector } from "../store";
import { fetchPortfolioSummary, fetchPortfolioRisk, fetchRebalancingSuggestions } from "../store/slices/portfolioSlice";
import RiskMeter from "../components/Portfolio/RiskMeter";
import AssetCard from "../components/Portfolio/AssetCard";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";

const Portfolio: React.FC = () => {
  const dispatch = useAppDispatch();
  const { user } = useAppSelector((state) => state.auth);
  const { summary, risk, rebalancingSuggestions, isLoading } = useAppSelector((state) => state.portfolio);
  const isHe = user?.preferred_language === "he";
  const [showRebalancing, setShowRebalancing] = useState(false);

  useEffect(() => {
    dispatch(fetchPortfolioSummary());
    dispatch(fetchPortfolioRisk());
    dispatch(fetchRebalancingSuggestions());
  }, [dispatch]);

  const formatCurrency = (v: number) =>
    `₪${Math.abs(v).toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold print-header">{isHe ? "תיק ההשקעות שלי" : "My Portfolio"}</h1>
        <div className="flex items-center gap-2">
          {rebalancingSuggestions.length > 0 && (
            <button
              onClick={() => setShowRebalancing(!showRebalancing)}
              className="no-print text-sm bg-yellow-600/20 border border-yellow-600/50 text-yellow-400 px-4 py-2 rounded-xl hover:bg-yellow-600/30"
            >
              {isHe ? `${rebalancingSuggestions.length} הצעות איזון` : `${rebalancingSuggestions.length} Rebalancing Tips`}
            </button>
          )}
          <button
            onClick={() => window.print()}
            className="no-print text-sm bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 hover:text-white rounded-xl px-4 py-2 transition-colors flex items-center gap-2"
          >
            <span>📄</span>
            {isHe ? "ייצוא PDF" : "Export PDF"}
          </button>
        </div>
      </div>

      {/* Summary Row */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label_he: "שווי כולל", label_en: "Total Value", value: formatCurrency(summary.total_value), color: "text-white" },
            { label_he: "מזומן", label_en: "Cash", value: formatCurrency(summary.cash_balance), color: "text-green-400" },
            { label_he: "רווח/הפסד", label_en: "P&L", value: `${summary.total_pnl >= 0 ? "+" : ""}${formatCurrency(summary.total_pnl)}`, color: summary.total_pnl >= 0 ? "text-green-400" : "text-red-400" },
            { label_he: "עמדות פתוחות", label_en: "Positions", value: String(summary.position_count), color: "text-blue-400" },
          ].map((item) => (
            <div key={item.label_en} className="bg-gray-900 rounded-2xl p-4 border border-gray-800">
              <p className="text-gray-400 text-xs mb-1">{isHe ? item.label_he : item.label_en}</p>
              <p className={`text-xl font-bold ${item.color}`}>{item.value}</p>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Risk Meter */}
        {risk && (
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
            <h2 className="font-bold mb-4">{isHe ? "מד סיכון" : "Risk Meter"}</h2>
            <RiskMeter score={risk.risk_score} level={risk.risk_level} />
            <div className="mt-4 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-gray-400">{isHe ? "חשיפת סיכון גבוה" : "High Risk Exposure"}</span>
                <span className="text-red-400">{risk.high_risk_exposure_pct.toFixed(1)}%</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-400">{isHe ? "ציון גיוון" : "Diversification"}</span>
                <span className="text-blue-400">{risk.diversification_score}/100</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-400">{isHe ? "מזומן" : "Cash"}</span>
                <span className="text-green-400">{risk.cash_pct.toFixed(1)}%</span>
              </div>
            </div>
          </div>
        )}

        {/* Holdings */}
        <div className="lg:col-span-2 space-y-4">
          <h2 className="font-bold">{isHe ? "אחזקות" : "Holdings"}</h2>
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-20 bg-gray-900 rounded-2xl animate-pulse" />
              ))}
            </div>
          ) : summary?.positions && summary.positions.length > 0 ? (
            <div className="space-y-3">
              {summary.positions.map((pos) => (
                <AssetCard key={pos.symbol} position={pos} isHe={isHe} />
              ))}
            </div>
          ) : (
            <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800 text-center text-gray-500">
              <p className="text-4xl mb-3">📊</p>
              <p>{isHe ? "אין אחזקות עדיין" : "No holdings yet"}</p>
              <p className="text-sm mt-1">{isHe ? "בדוק את המלצות ה-AI לרכישה" : "Check AI recommendations to start"}</p>
            </div>
          )}
        </div>
      </div>

      {/* Sector Allocation Pie Chart */}
      {summary?.positions && summary.positions.length > 0 && (() => {
        const PIE_COLORS = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6"];
        const hasSector = summary.positions.some(p => p.sector);
        let chartData: { name: string; value: number }[];

        if (hasSector) {
          const sectorMap: Record<string, number> = {};
          summary.positions.forEach(p => {
            const key = p.sector || (isHe ? "אחר" : "Other");
            sectorMap[key] = (sectorMap[key] || 0) + p.current_value;
          });
          chartData = Object.entries(sectorMap).map(([name, value]) => ({ name, value }));
        } else {
          const sorted = [...summary.positions].sort((a, b) => b.current_value - a.current_value);
          const top5 = sorted.slice(0, 5);
          const rest = sorted.slice(5);
          chartData = top5.map(p => ({ name: p.symbol, value: p.current_value }));
          if (rest.length > 0) {
            const otherValue = rest.reduce((acc, p) => acc + p.current_value, 0);
            chartData.push({ name: isHe ? "אחר" : "Other", value: otherValue });
          }
        }

        const total = chartData.reduce((acc, d) => acc + d.value, 0);

        return (
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
            <h2 className="font-bold mb-4">{isHe ? "הקצאה לפי סקטור" : "Allocation by Sector"}</h2>
            <div className="flex items-center gap-6">
              <div className="w-48 h-48 flex-shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={chartData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" paddingAngle={2}>
                      {chartData.map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value: number) => [`₪${value.toLocaleString("en", { maximumFractionDigits: 0 })}`, ""]}
                      contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: "8px", color: "#f9fafb" }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="flex-1 space-y-2">
                {chartData.map((d, i) => (
                  <div key={d.name} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }} />
                      <span className="text-gray-300">{d.name}</span>
                    </div>
                    <span className="text-gray-400 font-medium">{total > 0 ? ((d.value / total) * 100).toFixed(1) : 0}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        );
      })()}

      {/* Rebalancing Suggestions */}
      {showRebalancing && rebalancingSuggestions.length > 0 && (
        <div className="bg-gray-900 rounded-2xl p-6 border border-yellow-700/30">
          <h2 className="font-bold mb-4 text-yellow-400">
            {isHe ? "הצעות לאיזון תיק" : "Rebalancing Suggestions"}
          </h2>
          <div className="space-y-3">
            {rebalancingSuggestions.map((s, i) => (
              <div key={i} className={`p-4 rounded-xl border ${
                s.priority === "HIGH" ? "border-red-700/50 bg-red-900/10" : "border-yellow-700/50 bg-yellow-900/10"
              }`}>
                <div className="flex items-start gap-3">
                  <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                    s.priority === "HIGH" ? "bg-red-600 text-white" : "bg-yellow-600 text-white"
                  }`}>
                    {s.priority}
                  </span>
                  <p className="text-sm">{s.message}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default Portfolio;
