import React, { useEffect, useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { performanceApi } from "../../api/client";

interface Props {
  isHe: boolean;
}

const BacktestChart: React.FC<Props> = ({ isHe }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    performanceApi
      .getBacktest(100000)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  const fmt = (v: number) =>
    `₪${v.toLocaleString("en", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const val = payload[0]?.value;
    const ret = payload[0]?.payload?.return_pct;
    return (
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-3 text-xs space-y-1 shadow-xl">
        <p className="text-gray-400 font-medium">{label}</p>
        <p className="text-white font-bold">{fmt(val)}</p>
        {ret !== undefined && (
          <p className={ret >= 0 ? "text-green-400" : "text-red-400"}>
            {ret > 0 ? "+" : ""}{ret.toFixed(2)}% {isHe ? "החודש" : "this month"}
          </p>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6">
        <div className="h-6 w-48 bg-gray-800 rounded animate-pulse mb-4" />
        <div className="h-56 bg-gray-800 rounded animate-pulse" />
      </div>
    );
  }

  if (!data || data.data_points?.length === 0) {
    return (
      <div className="bg-gray-900 rounded-2xl border border-gray-800 p-8 text-center">
        <p className="text-3xl mb-3">📊</p>
        <p className="text-gray-400 font-medium">
          {isHe ? "נתוני בקטסט אינם זמינים" : "Backtest data not available yet"}
        </p>
        <p className="text-gray-600 text-sm mt-1">
          {data?.message ||
            (isHe
              ? "יהיו זמינים לאחר 2+ המלצות עם תוצאות"
              : "Available after 2+ recommendations with outcomes")}
        </p>
      </div>
    );
  }

  const { initial_capital, final_value, total_return_pct, max_drawdown_pct, sharpe_ratio, win_rate_pct, total_trades, data_points } = data;
  const isPositive = total_return_pct >= 0;
  const areaColor = isPositive ? "#22c55e" : "#ef4444";
  const gradientId = "backtestGradient";

  const kpis = [
    {
      label: isHe ? "תשואה כוללת" : "Total Return",
      value: `${total_return_pct > 0 ? "+" : ""}${total_return_pct?.toFixed(2)}%`,
      color: isPositive ? "text-green-400" : "text-red-400",
    },
    {
      label: isHe ? "ירידה מקסימלית" : "Max Drawdown",
      value: `-${max_drawdown_pct?.toFixed(2)}%`,
      color: "text-red-400",
    },
    {
      label: isHe ? "יחס שארפ" : "Sharpe Ratio",
      value: sharpe_ratio?.toFixed(2),
      color: sharpe_ratio >= 1 ? "text-green-400" : sharpe_ratio >= 0 ? "text-yellow-400" : "text-red-400",
    },
    {
      label: isHe ? "אחוז הצלחה" : "Win Rate",
      value: `${win_rate_pct?.toFixed(1)}%`,
      color: win_rate_pct >= 55 ? "text-green-400" : win_rate_pct >= 45 ? "text-yellow-400" : "text-red-400",
    },
  ];

  return (
    <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6 print-section">
      {/* Header */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <h3 className="font-bold text-lg">
            {isHe ? "בדיקה רטרוספקטיבית (בקטסט)" : "Backtest Simulation"}
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">
            {isHe
              ? `₪${initial_capital?.toLocaleString("en")} מושקע שווה בכל ${total_trades} המלצות`
              : `₪${initial_capital?.toLocaleString("en")} equal-weight across ${total_trades} recommendations`}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-gray-500">{isHe ? "ערך סופי" : "Final Value"}</p>
          <p className={`text-xl font-bold ${isPositive ? "text-green-400" : "text-red-400"}`}>
            {fmt(final_value)}
          </p>
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="bg-gray-800/60 rounded-xl p-3 text-center">
            <p className="text-xs text-gray-500 mb-1">{kpi.label}</p>
            <p className={`font-bold text-lg ${kpi.color}`}>{kpi.value}</p>
          </div>
        ))}
      </div>

      {/* Chart */}
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data_points} margin={{ top: 4, right: 4, bottom: 0, left: 8 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={areaColor} stopOpacity={0.25} />
                <stop offset="95%" stopColor={areaColor} stopOpacity={0.03} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
            <XAxis
              dataKey="month"
              tick={{ fill: "#6b7280", fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => v.slice(5)}
            />
            <YAxis
              tick={{ fill: "#6b7280", fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => `₪${(v / 1000).toFixed(0)}k`}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine y={initial_capital} stroke="#4b5563" strokeDasharray="4 4" />
            <Area
              type="monotone"
              dataKey="value"
              stroke={areaColor}
              strokeWidth={2}
              fill={`url(#${gradientId})`}
              dot={false}
              activeDot={{ r: 4, fill: areaColor }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <p className="text-xs text-gray-600 mt-3 text-center">
        {isHe
          ? "* הבקטסט מחולק שווה בין כל ההמלצות. ביצועי העבר אינם מבטיחים תוצאות עתידיות."
          : "* Equal-weight simulation across all recommendations. Past performance does not guarantee future results."}
      </p>
    </div>
  );
};

export default BacktestChart;
