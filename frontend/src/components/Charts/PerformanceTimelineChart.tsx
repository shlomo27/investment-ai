import React, { useEffect, useState } from "react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { performanceApi } from "../../api/client";

interface Props {
  isHe?: boolean;
}

const CustomTooltip = ({ active, payload, label, isHe }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-xs shadow-lg">
      <p className="text-gray-400 mb-2 font-medium">{label}</p>
      <p className="text-white mb-1">{isHe ? "סה\"כ עסקאות:" : "Total trades:"} {d?.total}</p>
      <p className="text-green-400 mb-1">{isHe ? "ניצחונות:" : "Wins:"} {d?.wins}</p>
      <p className="text-red-400 mb-1">{isHe ? "הפסדים:" : "Losses:"} {d?.losses}</p>
      <p className="text-blue-400 mb-1">{isHe ? "אחוז הצלחה:" : "Win rate:"} {d?.win_rate}%</p>
      <p className={`font-bold mt-1 ${d?.avg_return >= 0 ? "text-green-300" : "text-red-300"}`}>
        {isHe ? "תשואה ממוצעת:" : "Avg return:"} {d?.avg_return > 0 ? "+" : ""}{d?.avg_return}%
      </p>
    </div>
  );
};

const PerformanceTimelineChart: React.FC<Props> = ({ isHe = false }) => {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    performanceApi.getTimeline()
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="bg-gray-900 rounded-2xl border border-gray-800 animate-pulse h-64" />;

  if (!data.length) {
    return (
      <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 flex items-center justify-center h-64 text-gray-500 text-sm">
        {isHe ? "אין נתונים להצגה עדיין" : "No timeline data yet"}
      </div>
    );
  }

  const formatMonth = (m: string) => {
    const [year, month] = m.split("-");
    return new Date(parseInt(year), parseInt(month) - 1, 1)
      .toLocaleDateString(isHe ? "he-IL" : "en-US", { month: "short", year: "2-digit" });
  };

  const points = data.map((d) => ({ ...d, label: formatMonth(d.month) }));

  return (
    <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">
      <div className="p-5 border-b border-gray-800">
        <h2 className="font-bold text-base">
          {isHe ? "ביצועים חודשיים — אחוז הצלחה ותשואה" : "Monthly Performance — Win Rate & Return"}
        </h2>
        <p className="text-xs text-gray-500 mt-0.5">
          {isHe ? "פירוט לפי חודש של המלצות שמעקבן הושלם" : "Month-by-month breakdown of tracked recommendations"}
        </p>
      </div>
      <div className="p-5">
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis
              dataKey="label"
              tick={{ fill: "#6b7280", fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: "#1f2937" }}
            />
            <YAxis
              yAxisId="count"
              tick={{ fill: "#6b7280", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={28}
            />
            <YAxis
              yAxisId="rate"
              orientation="right"
              tick={{ fill: "#6b7280", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v}%`}
              width={40}
            />
            <Tooltip content={<CustomTooltip isHe={isHe} />} />
            <ReferenceLine yAxisId="rate" y={50} stroke="#374151" strokeDasharray="4 4" />
            <Bar yAxisId="count" dataKey="wins" fill="#22c55e" opacity={0.8} name={isHe ? "ניצחונות" : "Wins"} stackId="a" />
            <Bar yAxisId="count" dataKey="losses" fill="#ef4444" opacity={0.7} name={isHe ? "הפסדים" : "Losses"} stackId="a" />
            <Line
              yAxisId="rate"
              type="monotone"
              dataKey="win_rate"
              stroke="#60a5fa"
              strokeWidth={2.5}
              dot={{ fill: "#60a5fa", r: 3 }}
              name={isHe ? "% הצלחה" : "Win Rate %"}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default PerformanceTimelineChart;
