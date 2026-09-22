import React, { useEffect, useState } from "react";
import { useT } from "../i18n/t";
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

  // The i18n t(), not a local Hebrew/English switch. This screen shadowed it
  // with `t(he, en)`, so a French reader got Hebrew: the local helper had no
  // third case, and the Hebrew string sat where the dictionary key belongs.
  const t = useT();

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

  if (loading) return <div style={{ color: "#64748b", padding: 16 }}>{t("Loading...", "טוען...")}</div>;
  if (!sectors.length) return (
    <div style={{ color: "#64748b", padding: 16, textAlign: "center" }}>
      {t("No sector data available yet", "אין נתוני סקטורים")}
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
                  <span style={{ color: "#64748b", fontSize: 12 }}>{s.recommendation_count} {t("recs", "המלצות")}</span>
                  <span style={{ color: "#64748b", fontSize: 12 }}>{t("conf", "ביטחון")}: {s.avg_confidence}%</span>
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
