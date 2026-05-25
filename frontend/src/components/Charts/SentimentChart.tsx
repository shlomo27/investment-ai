import React from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Cell,
} from "recharts";

interface SentimentPoint {
  date: string;
  score: number;
  mentions?: number;
}

interface Props {
  data?: SentimentPoint[];
  symbol?: string;
  height?: number;
}

// Generate mock sentiment data
const generateMockSentimentData = (days = 14): SentimentPoint[] => {
  const data: SentimentPoint[] = [];
  const now = new Date();
  for (let i = days; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);
    const score = parseFloat((Math.random() * 2 - 1).toFixed(3));
    data.push({
      date: date.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      score,
      mentions: Math.floor(Math.random() * 5000 + 100),
    });
  }
  return data;
};

const SentimentChart: React.FC<Props> = ({ data, symbol, height = 160 }) => {
  const chartData = data || generateMockSentimentData();

  return (
    <div className="w-full">
      {symbol && (
        <p className="text-xs text-gray-400 mb-2">{symbol} Social Sentiment</p>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={chartData}
          margin={{ top: 5, right: 5, left: -30, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: "#6b7280", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: "#6b7280", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            domain={[-1, 1]}
            tickFormatter={(v) => v.toFixed(1)}
            width={35}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#111827",
              border: "1px solid #374151",
              borderRadius: "8px",
              color: "#f9fafb",
              fontSize: "12px",
            }}
            formatter={(value: number) => [
              `${value > 0 ? "+" : ""}${value.toFixed(3)}`,
              "Sentiment",
            ]}
          />
          <ReferenceLine y={0} stroke="#374151" strokeDasharray="3 3" />
          <Bar dataKey="score" radius={[2, 2, 0, 0]}>
            {chartData.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.score >= 0 ? "#22c55e" : "#ef4444"}
                fillOpacity={0.7}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex justify-center gap-4 mt-1">
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 bg-green-500 rounded" />
          <span className="text-xs text-gray-500">Bullish</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 bg-red-500 rounded" />
          <span className="text-xs text-gray-500">Bearish</span>
        </div>
      </div>
    </div>
  );
};

export default SentimentChart;
