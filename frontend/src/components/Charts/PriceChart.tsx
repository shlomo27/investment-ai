import React from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

interface PricePoint {
  date: string;
  price: number;
  volume?: number;
}

interface Props {
  data?: PricePoint[];
  symbol?: string;
  isPositive?: boolean;
  height?: number;
}

// Generate mock data if no data provided
const generateMockData = (days = 30): PricePoint[] => {
  const data: PricePoint[] = [];
  let price = 100 + Math.random() * 100;
  const now = new Date();
  for (let i = days; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);
    price = price * (1 + (Math.random() - 0.48) * 0.03);
    data.push({
      date: date.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      price: parseFloat(price.toFixed(2)),
    });
  }
  return data;
};

const PriceChart: React.FC<Props> = ({
  data,
  symbol,
  isPositive = true,
  height = 200,
}) => {
  const chartData = data || generateMockData();
  const color = isPositive ? "#22c55e" : "#ef4444";
  const gradientId = `gradient-${symbol || "chart"}-${isPositive ? "pos" : "neg"}`;

  return (
    <div className="w-full">
      {symbol && (
        <p className="text-xs text-gray-400 mb-2">{symbol} Price Chart</p>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart
          data={chartData}
          margin={{ top: 5, right: 5, left: -20, bottom: 5 }}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.2} />
              <stop offset="95%" stopColor={color} stopOpacity={0.01} />
            </linearGradient>
          </defs>
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
            tickFormatter={(v) => `₪${v.toFixed(0)}`}
            width={50}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#111827",
              border: "1px solid #374151",
              borderRadius: "8px",
              color: "#f9fafb",
              fontSize: "12px",
            }}
            formatter={(value: number) => [`₪${value.toFixed(2)}`, "Price"]}
          />
          <Area
            type="monotone"
            dataKey="price"
            stroke={color}
            strokeWidth={2}
            fill={`url(#${gradientId})`}
            dot={false}
            activeDot={{ r: 4, fill: color }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};

export default PriceChart;
