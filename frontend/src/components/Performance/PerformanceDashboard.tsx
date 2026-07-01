import React, { useEffect, useState } from "react";
import { performanceApi } from "../../api/client";

interface PerformanceSummary {
  total_tracked: number;
  win_count: number;
  loss_count: number;
  neutral_count: number;
  win_rate_pct: number;
  avg_return_pct: number;
  avg_vs_market_pct: number;
  best_trade: { symbol: string; return_pct: number; type: string; date: string } | null;
  worst_trade: { symbol: string; return_pct: number; type: string; date: string } | null;
  recent_outcomes: any[];
}

interface Props {
  isHebrew?: boolean;
}

const t = (he: string, en: string, isHe: boolean) => (isHe ? he : en);

export default function PerformanceDashboard({ isHebrew = true }: Props) {
  const [summary, setSummary] = useState<PerformanceSummary | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"summary" | "history">("summary");

  useEffect(() => {
    (async () => {
      try {
        const [s, h] = await Promise.all([
          performanceApi.getSummary(),
          performanceApi.getHistory(20, false),
        ]);
        setSummary(s);
        setHistory(h);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <div style={{ padding: 24, color: "#888" }}>{t("טוען ביצועים...", "Loading performance...", isHebrew)}</div>;
  if (!summary) return null;

  const resultColor = (r: string | null) =>
    r === "WIN" ? "#22c55e" : r === "LOSS" ? "#ef4444" : "#9ca3af";
  const returnColor = (v: number | null) => (v == null ? "#888" : v >= 0 ? "#22c55e" : "#ef4444");

  return (
    <div style={{ padding: 20 }}>
      <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
        {(["summary", "history"] as const).map((tb) => (
          <button
            key={tb}
            onClick={() => setTab(tb)}
            style={{
              padding: "8px 16px",
              borderRadius: 8,
              border: "none",
              cursor: "pointer",
              background: tab === tb ? "#3b82f6" : "#1e293b",
              color: tab === tb ? "#fff" : "#9ca3af",
              fontWeight: tab === tb ? 600 : 400,
            }}
          >
            {tb === "summary"
              ? t("סיכום ביצועים", "Performance Summary", isHebrew)
              : t("היסטוריה", "History", isHebrew)}
          </button>
        ))}
      </div>

      {tab === "summary" && (
        <div>
          {summary.total_tracked === 0 ? (
            <div style={{ color: "#888", textAlign: "center", padding: 40 }}>
              {t(
                "אין עדיין המלצות במעקב (יופיעו לאחר 30 יום מיום האישור)",
                "No tracked outcomes yet (appear 30 days after approval)",
                isHebrew
              )}
            </div>
          ) : (
            <>
              {/* KPI cards */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 16, marginBottom: 24 }}>
                {[
                  { label: t("סה\"כ במעקב", "Total Tracked", isHebrew), value: summary.total_tracked, color: "#fff" },
                  { label: t("אחוז הצלחה", "Win Rate", isHebrew), value: `${summary.win_rate_pct}%`, color: "#22c55e" },
                  { label: t("תשואה ממוצעת", "Avg Return", isHebrew), value: `${summary.avg_return_pct > 0 ? "+" : ""}${summary.avg_return_pct}%`, color: returnColor(summary.avg_return_pct) },
                  { label: t("alpha vs S&P500", "vs S&P 500", isHebrew), value: `${summary.avg_vs_market_pct > 0 ? "+" : ""}${summary.avg_vs_market_pct}%`, color: returnColor(summary.avg_vs_market_pct) },
                  { label: t("ניצחונות", "Wins", isHebrew), value: summary.win_count, color: "#22c55e" },
                  { label: t("הפסדים", "Losses", isHebrew), value: summary.loss_count, color: "#ef4444" },
                ].map((kpi) => (
                  <div key={kpi.label} style={{ background: "#1e293b", borderRadius: 12, padding: 16, textAlign: "center" }}>
                    <div style={{ color: "#64748b", fontSize: 12, marginBottom: 4 }}>{kpi.label}</div>
                    <div style={{ color: kpi.color, fontSize: 22, fontWeight: 700 }}>{kpi.value}</div>
                  </div>
                ))}
              </div>

              {/* Best / Worst */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
                {summary.best_trade && (
                  <div style={{ background: "#0f2d1c", border: "1px solid #22c55e", borderRadius: 12, padding: 16 }}>
                    <div style={{ color: "#22c55e", fontWeight: 600, marginBottom: 8 }}>🏆 {t("עסקה מוצלחת ביותר", "Best Trade", isHebrew)}</div>
                    <div style={{ color: "#fff", fontSize: 18, fontWeight: 700 }}>{summary.best_trade.symbol}</div>
                    <div style={{ color: "#22c55e" }}>+{summary.best_trade.return_pct}%</div>
                    <div style={{ color: "#64748b", fontSize: 12 }}>{summary.best_trade.type}</div>
                  </div>
                )}
                {summary.worst_trade && (
                  <div style={{ background: "#2d0f0f", border: "1px solid #ef4444", borderRadius: 12, padding: 16 }}>
                    <div style={{ color: "#ef4444", fontWeight: 600, marginBottom: 8 }}>📉 {t("עסקה גרועה ביותר", "Worst Trade", isHebrew)}</div>
                    <div style={{ color: "#fff", fontSize: 18, fontWeight: 700 }}>{summary.worst_trade.symbol}</div>
                    <div style={{ color: "#ef4444" }}>{summary.worst_trade.return_pct}%</div>
                    <div style={{ color: "#64748b", fontSize: 12 }}>{summary.worst_trade.type}</div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {tab === "history" && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ color: "#64748b", borderBottom: "1px solid #334155" }}>
                {[t("סימול", "Symbol", isHebrew), t("המלצה", "Type", isHebrew), t("מחיר כניסה", "Entry", isHebrew),
                  t("מחיר יציאה", "Exit", isHebrew), t("תשואה", "Return", isHebrew), t("vs שוק", "vs Mkt", isHebrew), t("תוצאה", "Result", isHebrew)]
                  .map((h) => <th key={h} style={{ padding: "8px 12px", textAlign: "left" }}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {history.map((r) => (
                <tr key={r.id} style={{ borderBottom: "1px solid #1e293b" }}>
                  <td style={{ padding: "8px 12px", color: "#fff", fontWeight: 600 }}>{r.symbol}</td>
                  <td style={{ padding: "8px 12px", color: "#94a3b8" }}>{r.type}</td>
                  <td style={{ padding: "8px 12px", color: "#94a3b8" }}>{r.entry_price ? `$${r.entry_price.toFixed(2)}` : "—"}</td>
                  <td style={{ padding: "8px 12px", color: "#94a3b8" }}>{r.outcome_price ? `$${r.outcome_price.toFixed(2)}` : t("ממתין", "Pending", isHebrew)}</td>
                  <td style={{ padding: "8px 12px", color: returnColor(r.outcome_return_pct) }}>
                    {r.outcome_return_pct != null ? `${r.outcome_return_pct > 0 ? "+" : ""}${r.outcome_return_pct.toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ padding: "8px 12px", color: returnColor(r.outcome_vs_market_pct) }}>
                    {r.outcome_vs_market_pct != null ? `${r.outcome_vs_market_pct > 0 ? "+" : ""}${r.outcome_vs_market_pct.toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ padding: "8px 12px" }}>
                    <span style={{ background: resultColor(r.outcome_result) + "22", color: resultColor(r.outcome_result), borderRadius: 6, padding: "2px 8px", fontSize: 12 }}>
                      {r.outcome_result || t("ממתין", "PENDING", isHebrew)}
                    </span>
                  </td>
                </tr>
              ))}
              {history.length === 0 && (
                <tr><td colSpan={7} style={{ textAlign: "center", color: "#64748b", padding: 40 }}>{t("אין נתונים", "No data yet", isHebrew)}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
