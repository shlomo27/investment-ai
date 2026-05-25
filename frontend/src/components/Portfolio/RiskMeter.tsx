import React from "react";

interface Props {
  score: number; // 0-100
  level: string;
}

const RiskMeter: React.FC<Props> = ({ score, level }) => {
  const clampedScore = Math.max(0, Math.min(100, score));

  // Color based on risk level
  const getColor = () => {
    if (clampedScore < 30) return "#22c55e"; // green
    if (clampedScore < 60) return "#eab308"; // yellow
    if (clampedScore < 80) return "#f97316"; // orange
    return "#ef4444"; // red
  };

  const color = getColor();

  // SVG arc calculation
  const radius = 70;
  const circumference = Math.PI * radius; // Half circle
  const strokeDashoffset = circumference - (clampedScore / 100) * circumference;

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-44 h-24">
        <svg
          viewBox="0 0 160 90"
          className="w-full h-full"
        >
          {/* Background arc */}
          <path
            d="M 10 80 A 70 70 0 0 1 150 80"
            fill="none"
            stroke="#374151"
            strokeWidth="12"
            strokeLinecap="round"
          />
          {/* Foreground arc */}
          <path
            d="M 10 80 A 70 70 0 0 1 150 80"
            fill="none"
            stroke={color}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            style={{ transition: "stroke-dashoffset 0.8s ease-in-out" }}
          />
          {/* Score text */}
          <text
            x="80"
            y="72"
            textAnchor="middle"
            fill="white"
            fontSize="22"
            fontWeight="bold"
            fontFamily="sans-serif"
          >
            {clampedScore}
          </text>
        </svg>
      </div>

      {/* Level badge */}
      <div
        className="mt-1 px-4 py-1 rounded-full text-sm font-bold"
        style={{ backgroundColor: `${color}22`, color }}
      >
        {level}
      </div>

      {/* Scale labels */}
      <div className="flex justify-between w-full mt-2 px-2">
        <span className="text-xs text-green-400">LOW</span>
        <span className="text-xs text-yellow-400">MED</span>
        <span className="text-xs text-red-400">HIGH</span>
      </div>
    </div>
  );
};

export default RiskMeter;
