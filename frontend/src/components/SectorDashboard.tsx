import React, { useEffect, useState } from "react";
import { marketExtApi } from "../api/client";

interface SectorData {
  sector: string;
  recommendation_count: number;
  avg_confidence: number;
  avg_expected_return_pct: number;
  signal: "BULLISH" | "BEARISH";
}

interface Props {
  isHebrew?: boolean;
}

export default function SectorDashboard({ isHebrew = true }: Props) {
  const [sectors, setSectors] = useState<SectorData[]>([]);
  const [loading, setLoading] = useState(true);

  const t = (he: string, en: string) => (isHebrew ? he : en);

  useEffect(() => {
    (async () => {
      try {
        const data = await marketExtApi.getSectors();
        setSectors(data.sectors || []);
      } catch {
        setSectors([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <div style={{ color: "#64748b", padding: 16 }}>{t("טוען...", "Loading...")}</div>;
  if (!sectors.length) return (
    <div style={{ color: "#64748b", padding: 16, textAlign: "center" }}>
      {t("אין נתוני סקטורים", "No sector data available yet")}
    </div>
  );

  const max = Math.max(...sectors.map(s => Math.abs(s.avg_expected_return_pct)));

  return (
    <div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {sectors.map((s) => {
          const barW = max > 0 ? Math.abs(s.avg_expected_return_pct) / max * 100 : 0;
          const isBull = s.signal === "BULLISH";
          return (
            <div key={s.sector} style={{ background: "#1e293b", borderRadius: 10, padding: "12px 16px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span style={{ color: "#fff", fontWeight: 600 }}>{s.sector}</span>
                <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                  <span style={{ color: "#64748b", fontSize: 12 }}>{s.recommendation_count} {t("המלצות", "recs")}</span>
                  <span style={{ color: "#64748b", fontSize: 12 }}>{t("ביטחון", "conf")}: {s.avg_confidence}%</span>
                  <span style={{ color: isBull ? "#22c55e" : "#ef4444", fontWeight: 700 }}>
                    {isBull ? "▲" : "▼"} {Math.abs(s.avg_expected_return_pct).toFixed(1)}%
                  </span>
                </div>
              </div>
              <div style={{ background: "#0f172a", borderRadius: 4, height: 6, overflow: "hidden" }}>
                <div style={{
                  width: `${barW}%`,
                  height: "100%",
                  background: isBull ? "#22c55e" : "#ef4444",
                  borderRadius: 4,
                  transition: "width 0.5s ease",
                }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
