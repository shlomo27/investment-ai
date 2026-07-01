import React, { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, ReferenceLine, Area, AreaChart,
} from "recharts";
import { performanceApi } from "../../api/client";

interface Props {
  isHe?: boolean;
}

const CustomTooltip = ({ active, payload, label, isHe }: any) => {
  if (!active || !payload?.length) return null;
  const ai = payload.find((p: any) => p.dataKey === "ai_value");
  const spy = payload.find((p: any) => p.dataKey === "spy_value");
  const alpha = ai && spy ? (ai.value - spy.value).toFixed(2) : null;
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-xs shadow-lg">
      <p className="text-gray-400 mb-2 font-medium">{label}</p>
      {ai && (
        <p className="text-green-400 mb-1">
          AI: ${ai.value.toFixed(2)} ({payload[0]?.payload?.ai_month_return > 0 ? "+" : ""}{payload[0]?.payload?.ai_month_return}%)
        </p>
      )}
      {spy && (
        <p className="text-blue-400 mb-1">
          S&P 500: ${spy.value.toFixed(2)} ({payload[0]?.payload?.spy_month_return > 0 ? "+" : ""}{payload[0]?.payload?.spy_month_return}%)
        </p>
      )}
      {alpha !== null && (
        <p className={`font-bold mt-1 ${parseFloat(alpha) >= 0 ? "text-green-300" : "text-red-300"}`}>
          Alpha: {parseFloat(alpha) >= 0 ? "+" : ""}{alpha}
        </p>
      )}
      {payload[0]?.payload?.trade_count !== undefined && (
        <p className="text-gray-500 mt-1">{payload[0].payload.trade_count} {isHe ? "עסקאות" : "trades"}</p>
      )}
    </div>
  );
};

const PerformanceComparisonChart: React.FC<Props> = ({ isHe = false }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    performanceApi.getComparison()
      .then(setData)
      .catch(() => setError(isHe ? "שגיאה בטעינת נתונים" : "Failed to load data"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 animate-pulse h-80" />
    );
  }

  if (error || !data) {
    return (
      <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 flex items-center justify-center h-80 text-gray-500 text-sm">
        {error || (isHe ? "אין נתונים מספיקים להשוואה" : "Not enough tracked outcomes yet")}
      </div>
    );
  }

  if (!data.data_points?.length) {
    return (
      <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 flex flex-col items-center justify-center h-80 text-center gap-3">
        <span className="text-4xl">📊</span>
        <p className="text-gray-400 text-sm">
          {isHe
            ? "הגרף יופיע לאחר שמספיק המלצות יצברו תוצאות (30 יום מאישור)"
            : "Chart appears once enough recommendations have tracked outcomes (30 days post-approval)"}
        </p>
      </div>
    );
  }

  const aiColor = "#22c55e";
  const spyColor = "#60a5fa";
  const aiWins = data.total_ai_return > data.total_spy_return;

  const formatMonth = (m: string) => {
    const [year, month] = m.split("-");
    const d = new Date(parseInt(year), parseInt(month) - 1, 1);
    return d.toLocaleDateString(isHe ? "he-IL" : "en-US", { month: "short", year: "2-digit" });
  };

  const points = data.data_points.map((d: any) => ({ ...d, label: formatMonth(d.month) }));

  return (
    <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="p-5 border-b border-gray-800">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="font-bold text-base">
              {isHe ? "AI מול S&P 500 — השוואה מצטברת" : "AI vs S&P 500 — Cumulative Return"}
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              {isHe ? "ערך היפותטי של $100 בהתחלה" : "Hypothetical $100 starting value"}
              {!data.using_real_spy && (
                <span className="ml-2 text-yellow-600">
                  {isHe ? "(SPY משוער)" : "(estimated SPY)"}
                </span>
              )}
            </p>
          </div>
          {/* Summary badges */}
          <div className="flex gap-3 items-center">
            <div className="text-right">
              <p className="text-xs text-gray-500">{isHe ? "AI תשואה" : "AI Return"}</p>
              <p className={`text-lg font-bold ${data.total_ai_return >= 0 ? "text-green-400" : "text-red-400"}`}>
                {data.total_ai_return > 0 ? "+" : ""}{data.total_ai_return}%
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-gray-500">S&P 500</p>
              <p className={`text-lg font-bold ${data.total_spy_return >= 0 ? "text-blue-400" : "text-red-400"}`}>
                {data.total_spy_return > 0 ? "+" : ""}{data.total_spy_return}%
              </p>
            </div>
            <div className={`px-3 py-1.5 rounded-xl text-sm font-bold border ${
              aiWins
                ? "bg-green-900/30 border-green-700/50 text-green-300"
                : "bg-red-900/30 border-red-700/50 text-red-300"
            }`}>
              Alpha {data.alpha > 0 ? "+" : ""}{data.alpha}%
            </div>
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="p-5">
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="aiGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={aiColor} stopOpacity={0.25} />
                <stop offset="95%" stopColor={aiColor} stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="spyGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={spyColor} stopOpacity={0.12} />
                <stop offset="95%" stopColor={spyColor} stopOpacity={0.01} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis
              dataKey="label"
              tick={{ fill: "#6b7280", fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: "#1f2937" }}
            />
            <YAxis
              tick={{ fill: "#6b7280", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `$${v}`}
              width={52}
            />
            <Tooltip content={<CustomTooltip isHe={isHe} />} />
            <ReferenceLine y={100} stroke="#374151" strokeDasharray="4 4" />
            <Area
              type="monotone"
              dataKey="spy_value"
              stroke={spyColor}
              strokeWidth={2}
              fill="url(#spyGrad)"
              dot={false}
              name="S&P 500"
            />
            <Area
              type="monotone"
              dataKey="ai_value"
              stroke={aiColor}
              strokeWidth={2.5}
              fill="url(#aiGrad)"
              dot={false}
              name="AI"
            />
            <Legend
              wrapperStyle={{ fontSize: 12, paddingTop: 12 }}
              formatter={(value) => (
                <span style={{ color: value === "AI" ? aiColor : spyColor }}>
                  {value === "AI" ? (isHe ? "המלצות AI" : "AI Recommendations") : "S&P 500"}
                </span>
              )}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default PerformanceComparisonChart;
