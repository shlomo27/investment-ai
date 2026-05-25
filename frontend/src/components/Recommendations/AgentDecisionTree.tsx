import React from "react";

interface Props {
  symbol: string;
  hasFundamental: boolean;
  hasSenior: boolean;
  hasTechnical: boolean;
  isHe?: boolean;
}

interface StageProps {
  icon: string;
  label: string;
  sublabel?: string;
  status: "complete" | "pending" | "skipped";
}

const Stage: React.FC<StageProps> = ({ icon, label, sublabel, status }) => {
  const colors = {
    complete: "border-green-600/50 bg-green-900/10 text-green-400",
    pending: "border-gray-700 bg-gray-800/50 text-gray-400",
    skipped: "border-gray-800 bg-gray-900/50 text-gray-600",
  };

  return (
    <div className={`flex flex-col items-center p-3 rounded-xl border ${colors[status]} min-w-[80px]`}>
      <span className={`text-2xl mb-1 ${status === "skipped" ? "opacity-30" : ""}`}>{icon}</span>
      <span className="text-xs font-medium text-center">{label}</span>
      {sublabel && <span className="text-xs text-gray-500 text-center">{sublabel}</span>}
      {status === "complete" && (
        <span className="mt-1 text-xs text-green-400">✓</span>
      )}
      {status === "pending" && (
        <span className="mt-1 text-xs text-gray-500">—</span>
      )}
    </div>
  );
};

const Arrow: React.FC<{ active: boolean }> = ({ active }) => (
  <div className={`flex-1 flex items-center justify-center ${active ? "text-green-400" : "text-gray-700"}`}>
    <div className="flex items-center gap-1">
      <div className={`h-0.5 flex-1 ${active ? "bg-green-600" : "bg-gray-700"}`} style={{ minWidth: "20px" }} />
      <span className="text-xs">▶</span>
    </div>
  </div>
);

const AgentDecisionTree: React.FC<Props> = ({
  symbol,
  hasFundamental,
  hasSenior,
  hasTechnical,
  isHe = false,
}) => {
  return (
    <div className="bg-gray-800/50 rounded-xl p-4">
      <p className="text-xs text-gray-400 mb-3">
        {isHe ? `צינור ניתוח AI עבור ${symbol}` : `AI Analysis Pipeline for ${symbol}`}
      </p>
      <div className="flex items-stretch gap-1">
        <Stage
          icon="📦"
          label={isHe ? "הפקיד" : "Data Fetcher"}
          sublabel={isHe ? "איסוף נתונים" : "Data Collection"}
          status="complete"
        />
        <Arrow active={hasFundamental} />
        <Stage
          icon="🔬"
          label={isHe ? "אנליסט" : "Fundamental"}
          sublabel={isHe ? "ניתוח בסיסי" : "Analysis"}
          status={hasFundamental ? "complete" : "pending"}
        />
        <Arrow active={hasSenior} />
        <Stage
          icon="👔"
          label={isHe ? "הבכיר" : "Senior"}
          sublabel={isHe ? "ועדת בכירים" : "Committee"}
          status={hasSenior ? "complete" : "pending"}
        />
        <Arrow active={hasTechnical} />
        <Stage
          icon="📈"
          label={isHe ? "טכני" : "Technical"}
          sublabel={isHe ? "עם דרישה" : "On-demand"}
          status={hasTechnical ? "complete" : "skipped"}
        />
      </div>
    </div>
  );
};

export default AgentDecisionTree;
