import React, { useState } from "react";
import { marketExtApi } from "../api/client";

interface Props {
  isHebrew?: boolean;
}

const METRICS = [
  { key: "price", label_he: "מחיר", label_en: "Price", format: (v: any) => v != null ? `$${Number(v).toFixed(2)}` : "—" },
  { key: "market_cap", label_he: "שווי שוק", label_en: "Mkt Cap", format: (v: any) => v ? `$${(v/1e9).toFixed(1)}B` : "—" },
  { key: "pe_ratio", label_he: "P/E", label_en: "P/E", format: (v: any) => v != null ? Number(v).toFixed(1) : "—" },
  { key: "forward_pe", label_he: "Forward P/E", label_en: "Fwd P/E", format: (v: any) => v != null ? Number(v).toFixed(1) : "—" },
  { key: "revenue_growth", label_he: "צמיחת הכנסות", label_en: "Rev Growth", format: (v: any) => v != null ? `${(v*100).toFixed(1)}%` : "—" },
  { key: "profit_margin", label_he: "מרווח רווח", label_en: "Profit Margin", format: (v: any) => v != null ? `${(v*100).toFixed(1)}%` : "—" },
  { key: "roe", label_he: "ROE", label_en: "ROE", format: (v: any) => v != null ? `${(v*100).toFixed(1)}%` : "—" },
  { key: "debt_to_equity", label_he: "חוב/הון", label_en: "D/E", format: (v: any) => v != null ? Number(v).toFixed(2) : "—" },
  { key: "dividend_yield", label_he: "תשואת דיבידנד", label_en: "Div Yield", format: (v: any) => v != null ? `${(v*100).toFixed(2)}%` : "—" },
  { key: "beta", label_he: "בטא", label_en: "Beta", format: (v: any) => v != null ? Number(v).toFixed(2) : "—" },
  { key: "sector", label_he: "סקטור", label_en: "Sector", format: (v: any) => v || "—" },
  { key: "analyst_recommendation", label_he: "המלצת אנליסטים", label_en: "Analyst Rec", format: (v: any) => v || "—" },
];

export default function StockComparison({ isHebrew = true }: Props) {
  const [input, setInput] = useState("");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const t = (he: string, en: string) => (isHebrew ? he : en);

  const compare = async () => {
    const symbols = input.toUpperCase().split(/[\s,]+/).filter(Boolean);
    if (symbols.length < 2) {
      setError(t("הזן לפחות 2 סימולים", "Enter at least 2 symbols"));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await marketExtApi.compareStocks(symbols);
      setData(result);
    } catch (e: any) {
      setError(t("שגיאה בטעינה", "Failed to load comparison"));
    } finally {
      setLoading(false);
    }
  };

  const better = (metric: string, values: (string | number | null)[]) => {
    const nums = values.map(v => typeof v === "number" ? v : null);
    if (nums.every(v => v === null)) return null;
    const goodHigher = ["price", "market_cap", "revenue_growth", "profit_margin", "roe", "dividend_yield"];
    const goodLower = ["pe_ratio", "forward_pe", "debt_to_equity", "beta"];
    if (goodHigher.some(m => metric.includes(m))) return nums.indexOf(Math.max(...nums.filter(v => v !== null) as number[]));
    if (goodLower.some(m => metric.includes(m))) {
      const valid = nums.filter(v => v !== null && v > 0) as number[];
      if (!valid.length) return null;
      const minVal = Math.min(...valid);
      return nums.indexOf(minVal);
    }
    return null;
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && compare()}
          placeholder={t("AAPL, MSFT, GOOGL", "AAPL, MSFT, GOOGL")}
          style={{
            flex: 1, padding: "10px 16px", borderRadius: 8, border: "1px solid #334155",
            background: "#1e293b", color: "#fff", fontSize: 14,
          }}
        />
        <button
          onClick={compare}
          disabled={loading}
          style={{ padding: "10px 20px", borderRadius: 8, border: "none", background: "#3b82f6", color: "#fff", cursor: "pointer", fontWeight: 600 }}
        >
          {loading ? t("משווה...", "Loading...") : t("השווה", "Compare")}
        </button>
      </div>

      {error && <div style={{ color: "#ef4444", marginBottom: 12 }}>{error}</div>}

      {data && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #334155" }}>
                <th style={{ padding: "10px 12px", color: "#64748b", textAlign: "left", minWidth: 140 }}>{t("מדד", "Metric")}</th>
                {data.symbols.map((sym: string) => (
                  <th key={sym} style={{ padding: "10px 12px", color: "#3b82f6", textAlign: "center", minWidth: 120 }}>{sym}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr style={{ borderBottom: "1px solid #1e293b" }}>
                <td style={{ padding: "8px 12px", color: "#64748b", fontSize: 12 }}>{t("שם", "Name")}</td>
                {data.symbols.map((sym: string) => (
                  <td key={sym} style={{ padding: "8px 12px", color: "#94a3b8", textAlign: "center" }}>
                    {data.comparison[sym]?.name || sym}
                  </td>
                ))}
              </tr>
              {METRICS.map((m) => {
                const values = data.symbols.map((sym: string) => data.comparison[sym]?.[m.key]);
                const bestIdx = better(m.key, values);
                return (
                  <tr key={m.key} style={{ borderBottom: "1px solid #0f172a" }}>
                    <td style={{ padding: "8px 12px", color: "#64748b" }}>{isHebrew ? m.label_he : m.label_en}</td>
                    {values.map((v: any, i: number) => (
                      <td key={i} style={{
                        padding: "8px 12px",
                        textAlign: "center",
                        color: bestIdx === i ? "#22c55e" : "#94a3b8",
                        fontWeight: bestIdx === i ? 700 : 400,
                        background: bestIdx === i ? "#0f2d1c" : "transparent",
                      }}>
                        {m.format(v)}
                        {bestIdx === i && <span style={{ marginLeft: 4, fontSize: 10 }}>✓</span>}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div style={{ color: "#475569", fontSize: 11, marginTop: 8 }}>
            ✓ = {t("ערך עדיף לפי המדד", "better value for this metric")}
          </div>
        </div>
      )}
    </div>
  );
}
