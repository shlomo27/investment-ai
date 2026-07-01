import React, { useEffect, useState } from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from "recharts";
import { performanceApi } from "../../api/client";

interface Props {
  isHe?: boolean;
  days?: number;
}

const CustomTooltip = ({ active, payload, label, isHe }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-xs shadow-lg">
      <p className="text-gray-400 mb-2">{label}</p>
      <p className="text-white font-bold mb-1">
        {isHe ? "שווי כולל:" : "Total:"} ₪{d?.total_value?.toLocaleString("en", { minimumFractionDigits: 2 })}
      </p>
      <p className="text-blue-400 mb-1">
        {isHe ? "שוק:" : "Market:"} ₪{d?.market_value?.toLocaleString("en", { minimumFractionDigits: 2 })}
      </p>
      <p className="text-gray-400 mb-1">
        {isHe ? "מזומן:" : "Cash:"} ₪{d?.cash_balance?.toLocaleString("en", { minimumFractionDigits: 2 })}
      </p>
      <p className={`font-bold mt-1 ${d?.total_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
        P&L: {d?.total_pnl >= 0 ? "+" : ""}₪{d?.total_pnl?.toFixed(2)} ({d?.total_pnl_pct?.toFixed(2)}%)
      </p>
    </div>
  );
};

const PortfolioHistoryChart: React.FC<Props> = ({ isHe = false, days = 90 }) => {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState(days);

  const load = (d: number) => {
    setLoading(true);
    performanceApi.getPortfolioHistory(d)
      .then(setData)
      .catch(() => setData([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(period); }, [period]);

  const PERIODS = [
    { label: isHe ? "30י" : "30D", value: 30 },
    { label: isHe ? "90י" : "90D", value: 90 },
    { label: isHe ? "180י" : "6M", value: 180 },
    { label: isHe ? "שנה" : "1Y", value: 365 },
  ];

  const formatDate = (d: string) =>
    new Date(d).toLocaleDateString(isHe ? "he-IL" : "en-US", { month: "short", day: "numeric" });

  const points = data.map((d) => ({ ...d, label: formatDate(d.date) }));

  const first = points[0]?.total_value;
  const last = points[points.length - 1]?.total_value;
  const change = first && last ? ((last - first) / first) * 100 : null;
  const positive = change === null || change >= 0;

  return (
    <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">
      <div className="p-5 border-b border-gray-800 flex items-center justify-between">
        <div>
          <h2 className="font-bold text-base">
            {isHe ? "ביצועי תיק לאורך זמן" : "Portfolio Performance Over Time"}
          </h2>
          {change !== null && (
            <p className={`text-xs mt-0.5 ${positive ? "text-green-400" : "text-red-400"}`}>
              {positive ? "▲" : "▼"} {Math.abs(change).toFixed(2)}% {isHe ? "בתקופה" : "in period"}
            </p>
          )}
        </div>
        <div className="flex gap-1">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              onClick={() => setPeriod(p.value)}
              className={`px-2.5 py-1 rounded-lg text-xs transition-colors ${
                period === p.value
                  ? "bg-blue-600/30 border border-blue-500/50 text-blue-300"
                  : "text-gray-500 hover:text-white"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="p-5">
        {loading ? (
          <div className="h-56 flex items-center justify-center">
            <div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full" />
          </div>
        ) : !points.length ? (
          <div className="h-56 flex flex-col items-center justify-center text-center gap-3">
            <span className="text-3xl">📈</span>
            <p className="text-gray-500 text-sm">
              {isHe
                ? "תמונת מצב יומית תיאסף החל מהיום. הגרף יופיע לאחר מספר ימים."
                : "Daily snapshots start accumulating today. Chart appears within a few days."}
            </p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={224}>
            <AreaChart data={points} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="portGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={positive ? "#22c55e" : "#ef4444"} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={positive ? "#22c55e" : "#ef4444"} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis
                dataKey="label"
                tick={{ fill: "#6b7280", fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: "#1f2937" }}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: "#6b7280", fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `₪${(v / 1000).toFixed(0)}k`}
                width={48}
              />
              <Tooltip content={<CustomTooltip isHe={isHe} />} />
              <Area
                type="monotone"
                dataKey="total_value"
                stroke={positive ? "#22c55e" : "#ef4444"}
                strokeWidth={2}
                fill="url(#portGrad)"
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
};

export default PortfolioHistoryChart;
