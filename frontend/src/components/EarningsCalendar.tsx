import React, { useEffect, useState } from "react";
import { marketExtApi } from "../api/client";

interface EarningsEvent {
  symbol: string;
  earnings_date: string;
  eps_estimate: number | null;
  days_until: number;
  is_imminent: boolean;
  quarter: number | null;
  year: number | null;
}

interface Props {
  symbols?: string[];
  isHebrew?: boolean;
  daysAhead?: number;
}

export default function EarningsCalendar({ symbols, isHebrew = true, daysAhead = 14 }: Props) {
  const [events, setEvents] = useState<EarningsEvent[]>([]);
  const [loading, setLoading] = useState(true);

  const t = (he: string, en: string) => (isHebrew ? he : en);

  useEffect(() => {
    (async () => {
      try {
        const data = await marketExtApi.getEarningsCalendar(
          symbols ? symbols.join(",") : undefined,
          daysAhead
        );
        setEvents(data);
      } catch {
        setEvents([]);
      } finally {
        setLoading(false);
      }
    })();
  }, [symbols?.join(","), daysAhead]);

  if (loading) return <div style={{ color: "#64748b", padding: 16 }}>{t("טוען...", "Loading...")}</div>;
  if (!events.length) return (
    <div style={{ color: "#64748b", padding: 16, textAlign: "center" }}>
      {t("אין דיווחי רווחים קרובים", "No upcoming earnings in this period")}
    </div>
  );

  return (
    <div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {events.map((ev) => (
          <div key={`${ev.symbol}-${ev.earnings_date}`} style={{
            background: ev.is_imminent ? "#1c1406" : "#1e293b",
            border: `1px solid ${ev.is_imminent ? "#f59e0b" : "#334155"}`,
            borderRadius: 10,
            padding: "12px 16px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}>
            <div>
              <span style={{ color: "#fff", fontWeight: 700, fontSize: 15 }}>{ev.symbol}</span>
              {ev.quarter && <span style={{ color: "#64748b", fontSize: 12, marginLeft: 8 }}>Q{ev.quarter} {ev.year}</span>}
              <div style={{ color: "#94a3b8", fontSize: 13, marginTop: 2 }}>
                📅 {ev.earnings_date}
                {ev.eps_estimate != null && (
                  <span style={{ marginLeft: 12 }}>EPS {t("תחזית", "est.")}: ${ev.eps_estimate.toFixed(2)}</span>
                )}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{
                background: ev.days_until <= 1 ? "#ef444422" : ev.days_until <= 3 ? "#f59e0b22" : "#1e293b",
                color: ev.days_until <= 1 ? "#ef4444" : ev.days_until <= 3 ? "#f59e0b" : "#64748b",
                borderRadius: 8,
                padding: "4px 10px",
                fontSize: 13,
                fontWeight: 600,
              }}>
                {ev.days_until === 0 ? t("היום!", "Today!") :
                 ev.days_until === 1 ? t("מחר", "Tomorrow") :
                 `${ev.days_until} ${t("ימים", "days")}`}
              </div>
              {ev.is_imminent && (
                <div style={{ color: "#f59e0b", fontSize: 11, marginTop: 4 }}>⚠️ {t("ממשמש ובא", "IMMINENT")}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
