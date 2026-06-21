import React, { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useAppSelector } from "../store";
import { recommendationsApi, ordersApi } from "../api/client";
import { Recommendation, RecommendationType, OrderType, QuantitativeModels } from "../types";
import ConfirmTradeModal from "../components/Trading/ConfirmTradeModal";

// ─── Helpers ────────────────────────────────────────────────────────────────────

const recColor = (type: string) => {
  if (type === "STRONG_BUY") return "bg-green-500/20 text-green-300 border-green-600/40";
  if (type === "BUY") return "bg-green-900/30 text-green-400 border-green-700/40";
  if (type === "STRONG_SELL") return "bg-red-500/20 text-red-300 border-red-600/40";
  if (type === "SELL") return "bg-red-900/30 text-red-400 border-red-700/40";
  return "bg-gray-800 text-gray-300 border-gray-700";
};

const directionBadge = (bias?: string) => {
  if (bias === "LONG") return "bg-green-900/40 text-green-300 border border-green-700/40";
  if (bias === "SHORT") return "bg-red-900/40 text-red-300 border border-red-700/40";
  return "bg-gray-800 text-gray-400 border border-gray-700";
};

const ScoreBar: React.FC<{ value: number; max?: number; color?: string }> = ({
  value, max = 100, color = "bg-blue-500",
}) => (
  <div className="flex items-center gap-2">
    <div className="flex-1 bg-gray-800 rounded-full h-1.5">
      <div className={`${color} h-1.5 rounded-full`} style={{ width: `${(value / max) * 100}%` }} />
    </div>
    <span className="text-xs text-gray-300 w-8 text-right">{value.toFixed(0)}</span>
  </div>
);

// ─── Quant model helpers ─────────────────────────────────────────────────────────

const upColor = (pct?: number) =>
  pct == null ? "text-gray-400" : pct >= 0 ? "text-green-400" : "text-red-400";

const fmtPct = (v?: number) =>
  v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;

const fmtUsd = (v?: number) =>
  v == null ? "—" : `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const fmtMM = (v?: number) =>
  v == null ? "—" : `$${v.toFixed(1)}M`;

// ─── Model detail modals ────────────────────────────────────────────────────────

const ModalShell: React.FC<{ title: string; subtitle: string; accentCls: string; onClose: () => void; children: React.ReactNode }> = ({
  title, subtitle, accentCls, onClose, children,
}) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
    <div
      className="bg-gray-950 border border-gray-800 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl"
      onClick={(e) => e.stopPropagation()}
    >
      <div className={`flex items-start justify-between px-6 py-4 border-b border-gray-800 sticky top-0 bg-gray-950`}>
        <div>
          <p className={`text-xs font-bold uppercase tracking-widest ${accentCls}`}>{subtitle}</p>
          <h3 className="text-lg font-bold text-gray-100 mt-0.5">{title}</h3>
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-xl leading-none mt-1">✕</button>
      </div>
      <div className="px-6 py-5 space-y-5">{children}</div>
    </div>
  </div>
);

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div>
    <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500 mb-2">{title}</p>
    {children}
  </div>
);

const Row: React.FC<{ label: string; value: React.ReactNode; cls?: string }> = ({ label, value, cls }) => (
  <div className="flex justify-between items-center py-1 border-b border-gray-800/50 text-sm">
    <span className="text-gray-400">{label}</span>
    <span className={`font-mono font-medium ${cls ?? "text-gray-200"}`}>{value}</span>
  </div>
);

const ResultBanner: React.FC<{ label: string; value: string; upside?: number }> = ({ label, value, upside }) => (
  <div className="bg-gray-800/60 rounded-xl p-4 flex items-center justify-between mt-2">
    <div>
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold font-mono text-gray-100 mt-0.5">{value}</p>
    </div>
    {upside != null && (
      <p className={`text-xl font-bold font-mono ${upColor(upside)}`}>{fmtPct(upside)}</p>
    )}
  </div>
);

// DCF Modal
const DCFModal: React.FC<{ dcf: NonNullable<QuantitativeModels["dcf"]>; onClose: () => void }> = ({ dcf, onClose }) => (
  <ModalShell title="Discounted Cash Flow (DCF)" subtitle="Intrinsic Valuation" accentCls="text-blue-400" onClose={onClose}>
    <Section title="Methodology">
      <p className="text-sm text-gray-400 leading-relaxed">
        DCF values a company by projecting its free cash flow forward 5 years, then adding a terminal value
        (the perpetuity value after Year 5). All future cash flows are discounted back to today using WACC
        (Weighted Average Cost of Capital). The resulting total equity value is divided by shares outstanding
        to derive intrinsic value per share.
      </p>
    </Section>

    <Section title="Assumptions">
      <Row label="FCF Base (TTM)" value={fmtMM(dcf.fcf_base_mm)} />
      <Row label="FCF Growth Rate (Years 1–5)" value={`${dcf.fcf_growth_pct}% / yr`} />
      <Row label="WACC (Discount Rate)" value={`${dcf.wacc_pct}%`} />
      <Row label="Terminal Growth Rate" value={`${dcf.terminal_growth_pct}%`} />
      <Row label="Implied Shares Outstanding" value={`${dcf.shares_mm}M`} />
      <p className="text-[10px] text-gray-600 mt-1">
        WACC = Risk-free 4.5% + Beta × Equity Risk Premium 5.5%. FCF growth capped at 30%.
      </p>
    </Section>

    {dcf.yearly_projections && dcf.yearly_projections.length > 0 && (
      <Section title="5-Year FCF Projection">
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="text-gray-500 border-b border-gray-800">
                <th className="text-left py-1.5 pr-4">Year</th>
                <th className="text-right py-1.5 pr-4">FCF ($M)</th>
                <th className="text-right py-1.5 pr-4">PV Factor</th>
                <th className="text-right py-1.5">PV ($M)</th>
              </tr>
            </thead>
            <tbody>
              {dcf.yearly_projections.map((yr) => (
                <tr key={yr.year} className="border-b border-gray-800/40">
                  <td className="py-1.5 pr-4 text-gray-400">Year {yr.year}</td>
                  <td className="py-1.5 pr-4 text-right text-gray-200">{yr.fcf_mm.toFixed(1)}</td>
                  <td className="py-1.5 pr-4 text-right text-gray-500">{yr.pv_factor.toFixed(4)}</td>
                  <td className="py-1.5 text-right text-blue-400">{yr.pv_mm.toFixed(1)}</td>
                </tr>
              ))}
              <tr className="border-t border-gray-700">
                <td colSpan={3} className="py-1.5 pr-4 text-gray-400">PV of 5-yr FCFs</td>
                <td className="py-1.5 text-right text-blue-300 font-bold">
                  ${(dcf.pv_5yr_fcf! / 1e6).toFixed(1)}M
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Section>
    )}

    <Section title="Terminal Value">
      <Row label="Terminal Value (Year 5 FCF × perpetuity)" value={`$${(dcf.terminal_value_total! / 1e6).toFixed(0)}M`} />
      <Row label="PV of Terminal Value" value={`$${(dcf.pv_terminal! / 1e6).toFixed(0)}M`} />
      <Row label="Total Equity Value (5yr FCF + Terminal)" value={`$${(dcf.total_equity! / 1e6).toFixed(0)}M`} />
    </Section>

    <ResultBanner label="Intrinsic Value per Share" value={fmtUsd(dcf.intrinsic_value)} upside={dcf.upside_pct} />
    <p className="text-[10px] text-gray-600 text-center">
      Current price {fmtUsd(dcf.current_price)} · WACC {dcf.wacc_pct}% · Terminal growth {dcf.terminal_growth_pct}%
    </p>
  </ModalShell>
);

// DDM Modal
const DDMModal: React.FC<{ ddm: NonNullable<QuantitativeModels["ddm"]>; onClose: () => void }> = ({ ddm, onClose }) => (
  <ModalShell title="Dividend Discount Model (DDM)" subtitle="Gordon Growth Model" accentCls="text-purple-400" onClose={onClose}>
    <Section title="Methodology">
      <p className="text-sm text-gray-400 leading-relaxed">
        The Gordon Growth Model values a stock as the present value of all future dividends growing at a constant
        rate. It is applicable only to dividend-paying stocks and assumes dividends grow perpetually at a
        sustainable rate derived from ROE and retention ratio. Formula: <span className="font-mono text-gray-300">P = D₁ / (ke − g)</span>
      </p>
    </Section>

    <Section title="Inputs">
      <Row label="Current Dividend per Share (D₀)" value={fmtUsd(ddm.dividend_per_share)} />
      <Row label="Next Year Dividend (D₁ = D₀ × (1+g))" value={fmtUsd(ddm.dividend_per_share != null ? ddm.dividend_per_share * (1 + (ddm.growth_rate_pct ?? 0) / 100) : undefined)} />
      <Row label="Sustainable Growth Rate (g)" value={`${ddm.growth_rate_pct}%`} />
      <Row label="Cost of Equity (ke)" value={`${ddm.cost_of_equity_pct}%`} />
      <Row label="ke − g (discount spread)" value={`${((ddm.cost_of_equity_pct ?? 0) - (ddm.growth_rate_pct ?? 0)).toFixed(1)}%`} />
      <p className="text-[10px] text-gray-600 mt-1">
        g = ROE × (1 − payout ratio), capped at 12%. ke = 4.5% + beta × 5.5%.
      </p>
    </Section>

    <Section title="Formula Application">
      <div className="bg-gray-800/50 rounded-xl p-4 font-mono text-sm text-center">
        <p className="text-gray-400">P = D₁ / (ke − g)</p>
        <p className="text-gray-200 mt-1">
          = {fmtUsd(ddm.dividend_per_share != null ? ddm.dividend_per_share * (1 + (ddm.growth_rate_pct ?? 0) / 100) : undefined)}
          {" ÷ "}({ddm.cost_of_equity_pct}% − {ddm.growth_rate_pct}%)
        </p>
        <p className="text-blue-300 mt-1 text-lg font-bold">= {fmtUsd(ddm.intrinsic_value)}</p>
      </div>
    </Section>

    <ResultBanner label="DDM Intrinsic Value" value={fmtUsd(ddm.intrinsic_value)} upside={ddm.upside_pct} />
    <p className="text-[10px] text-gray-600 text-center">
      Only valid for dividend-paying stocks. Sensitive to growth rate and cost of equity assumptions.
    </p>
  </ModalShell>
);

// Monte Carlo Modal
const MonteCarloModal: React.FC<{ mc: NonNullable<QuantitativeModels["monte_carlo"]>; price?: number; onClose: () => void }> = ({ mc, price, onClose }) => {
  const distData = [
    { label: "P10 — Bear", value: mc.p10, cls: "bg-red-700" },
    { label: "P25", value: mc.p25, cls: "bg-orange-700" },
    { label: "P50 ≈ Mean", value: mc.mean, cls: "bg-yellow-600" },
    { label: "P75", value: mc.p75, cls: "bg-lime-700" },
    { label: "P90 — Bull", value: mc.p90, cls: "bg-green-700" },
  ];
  const lo  = (mc.p10 ?? 0) * 0.93;
  const hi  = (mc.p90 ?? 1) * 1.07;
  const rng = hi - lo;
  const barPct = (v: number) => Math.max(2, Math.min(98, (v - lo) / rng * 100));

  return (
    <ModalShell title="Monte Carlo Simulation" subtitle="1 000 Paths · 1-Year Horizon" accentCls="text-amber-400" onClose={onClose}>
      <Section title="Methodology">
        <p className="text-sm text-gray-400 leading-relaxed">
          Runs 1,000 independent price paths using Geometric Brownian Motion (GBM) — the industry-standard
          stochastic model for asset prices. Each path simulates 252 trading days. Annual volatility is
          estimated as beta × 20% (market vol proxy). Annual drift is capped at 30% from revenue growth.
          Final prices are ranked to produce the percentile distribution.
        </p>
      </Section>

      <Section title="Parameters">
        <Row label="Current Price" value={fmtUsd(mc.current_price)} />
        <Row label="Annual Volatility (σ)" value={`${mc.annual_vol_pct}%`} />
        <Row label="Annual Drift (μ)" value={`${mc.annual_drift_pct}%`} />
        <Row label="Simulations" value={`${mc.simulations?.toLocaleString()}`} />
        <Row label="Horizon" value={`${mc.horizon_days} trading days (1 year)`} />
        <p className="text-[10px] text-gray-600 mt-1">σ = beta × market vol 20%. μ = revenue growth (capped 30%).</p>
      </Section>

      <Section title="Price Distribution at 1-Year Horizon">
        <div className="space-y-2 mt-1">
          {distData.map(({ label, value, cls }) => {
            if (value == null) return null;
            const pct = barPct(value);
            const isCurrent = price != null && Math.abs(value - price) < (price * 0.01);
            return (
              <div key={label} className="flex items-center gap-3">
                <span className="text-[10px] text-gray-500 w-20 shrink-0">{label}</span>
                <div className="flex-1 bg-gray-800 rounded-full h-2 relative">
                  <div className={`${cls} h-2 rounded-full`} style={{ width: `${pct}%` }} />
                </div>
                <span className={`font-mono text-xs w-20 text-right ${upColor(price ? (value - price) / price * 100 : 0)}`}>
                  {fmtUsd(value)}
                </span>
              </div>
            );
          })}
          {price != null && (
            <div className="flex items-center gap-3">
              <span className="text-[10px] text-white/50 w-20 shrink-0">▶ Current</span>
              <div className="flex-1 bg-gray-800 rounded-full h-2 relative">
                <div className="bg-white/40 h-2 rounded-full" style={{ width: `${barPct(price)}%` }} />
              </div>
              <span className="font-mono text-xs w-20 text-right text-white/60">{fmtUsd(price)}</span>
            </div>
          )}
        </div>
      </Section>

      <Section title="Probability Statistics">
        <Row
          label={`Probability price ends above ${fmtUsd(price ?? mc.current_price)}`}
          value={`${mc.prob_above_pct}%`}
          cls={upColor((mc.prob_above_pct ?? 50) - 50)}
        />
        <Row label="Expected mean price" value={fmtUsd(mc.mean)} cls={upColor(price ? (mc.mean ?? 0) - price : 0)} />
        {price && mc.mean != null && (
          <Row
            label="Mean implied upside"
            value={fmtPct((mc.mean - price) / price * 100)}
            cls={upColor((mc.mean - price) / price * 100)}
          />
        )}
      </Section>
    </ModalShell>
  );
};

// Comps Modal
const CompsModal: React.FC<{ comps: NonNullable<QuantitativeModels["comps"]>; onClose: () => void }> = ({ comps, onClose }) => {
  const cmp = comps.comparisons ?? {};
  const multiples: Array<{ key: "pe" | "pb" | "ps"; label: string; desc: string }> = [
    { key: "pe", label: "P/E Ratio", desc: "Price to Earnings — measures how much investors pay per dollar of earnings" },
    { key: "pb", label: "P/B Ratio", desc: "Price to Book — compares market value to accounting book value" },
    { key: "ps", label: "P/S Ratio", desc: "Price to Sales — useful for companies with negative earnings" },
  ];
  return (
    <ModalShell title="Comparable Company Analysis" subtitle={`Sector: ${comps.sector ?? "Unknown"}`} accentCls="text-cyan-400" onClose={onClose}>
      <Section title="Methodology">
        <p className="text-sm text-gray-400 leading-relaxed">
          Comps values a company by comparing its trading multiples to sector averages. If a stock trades at
          a discount to peers on P/E, P/B, or P/S, it may be undervalued. The implied fair value for each
          multiple is: <span className="font-mono text-gray-300">Implied Price = (Price / Company Multiple) × Sector Average Multiple</span>
        </p>
      </Section>

      {comps.sector_averages && (
        <Section title={`${comps.sector} Sector Averages`}>
          <div className="grid grid-cols-4 gap-2">
            {Object.entries(comps.sector_averages).map(([k, v]) => (
              <div key={k} className="bg-gray-800/60 rounded-lg p-2 text-center">
                <p className="text-[10px] text-gray-500 uppercase">{k.replace("_", "/")}</p>
                <p className="text-sm font-bold font-mono text-gray-200">{v}x</p>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-gray-600 mt-1">Source: static sector median multiples (updated periodically)</p>
        </Section>
      )}

      {multiples.map(({ key, label, desc }) => {
        const m = cmp[key];
        if (!m) return null;
        return (
          <Section key={key} title={label}>
            <p className="text-[10px] text-gray-600 mb-2">{desc}</p>
            <Row label="Company Multiple" value={`${m.company}x`} />
            <Row label="Sector Average" value={`${m.sector_avg}x`} />
            <Row
              label="Premium / Discount to Sector"
              value={`${m.premium_pct >= 0 ? "+" : ""}${m.premium_pct.toFixed(1)}%`}
              cls={m.premium_pct >= 0 ? "text-red-400" : "text-green-400"}
            />
            <Row label="Implied Fair Value at Sector Multiple" value={fmtUsd(m.implied_price)} />
            <Row label="Implied Upside / Downside" value={fmtPct(m.upside_pct)} cls={upColor(m.upside_pct)} />
          </Section>
        );
      })}

      {Object.keys(cmp).length === 0 && (
        <p className="text-sm text-gray-500 italic">No multiples available (missing P/E, P/B, P/S data)</p>
      )}
    </ModalShell>
  );
};

// Sensitivity Modal
const SensitivityModal: React.FC<{ sens: NonNullable<QuantitativeModels["sensitivity"]>; onClose: () => void }> = ({ sens, onClose }) => (
  <ModalShell title="Sensitivity Analysis" subtitle="P/E × EPS Growth Scenario Grid" accentCls="text-rose-400" onClose={onClose}>
    <Section title="Methodology">
      <p className="text-sm text-gray-400 leading-relaxed">
        Tests how share price changes across different combinations of EPS growth and P/E multiple expansion
        or contraction. This is a scenario-based model: each cell shows the implied price if earnings grow by
        the row's rate and the market re-rates the stock to the column's P/E multiple.
        Formula: <span className="font-mono text-gray-300">Implied Price = Current EPS × (1 + EPS Growth) × P/E Multiple</span>
      </p>
    </Section>

    <Section title="Base Inputs">
      <Row label="Current EPS (TTM)" value={`$${sens.current_eps}`} />
      <Row label="Current P/E Multiple" value={`${sens.current_pe}x`} />
      <Row label="Current Share Price" value={fmtUsd(sens.current_price)} />
    </Section>

    <Section title="Price Grid — EPS Growth vs P/E Multiple">
      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono border-collapse">
          <thead>
            <tr>
              <th className="text-left text-gray-500 pb-2 pr-3 whitespace-nowrap">EPS Growth ↓ / P/E →</th>
              {sens.pe_scenarios?.map((pe) => (
                <th key={pe} className="text-center text-gray-500 pb-2 px-2 whitespace-nowrap">{pe}x</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sens.growth_scenarios?.map((g) => {
              const row = sens.table?.[g];
              if (!row) return null;
              return (
                <tr key={g} className="border-t border-gray-800/60">
                  <td className="pr-3 py-2 text-gray-400 whitespace-nowrap">{g}</td>
                  {sens.pe_scenarios?.map((pe) => {
                    const v = row[String(pe)];
                    const current = sens.current_price ?? 0;
                    const diff = current > 0 ? (v - current) / current : 0;
                    const isCurrent = Math.abs(diff) < 0.02;
                    return (
                      <td key={pe} className={`text-center py-2 px-2 rounded ${
                        isCurrent
                          ? "ring-1 ring-white/30 text-white font-bold"
                          : diff > 0.20 ? "text-green-300 bg-green-900/20"
                          : diff > 0.05 ? "text-green-500"
                          : diff < -0.20 ? "text-red-300 bg-red-900/20"
                          : diff < -0.05 ? "text-red-500"
                          : "text-gray-400"
                      }`}>
                        ${v?.toFixed(0)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-3 mt-2 text-[10px] text-gray-600">
        <span><span className="text-green-300">■</span> &gt;20% upside</span>
        <span><span className="text-green-500">■</span> &gt;5% upside</span>
        <span><span className="text-white">■</span> ≈ current</span>
        <span><span className="text-red-500">■</span> &gt;5% downside</span>
        <span><span className="text-red-300">■</span> &gt;20% downside</span>
      </div>
    </Section>
  </ModalShell>
);

// ─── Summary cards + modal controller ────────────────────────────────────────────

type ModelKey = "dcf" | "ddm" | "monte_carlo" | "comps" | "sensitivity";

const QuantModels: React.FC<{ qm: QuantitativeModels; price?: number }> = ({ qm, price }) => {
  const [open, setOpen] = useState<ModelKey | null>(null);

  const dcf  = qm.dcf;
  const ddm  = qm.ddm;
  const mc   = qm.monte_carlo;
  const sens = qm.sensitivity;
  const comp = qm.comps;

  const anyModel = dcf || ddm || mc || sens || comp;
  if (!anyModel) return null;

  interface ModelCard {
    key: ModelKey;
    label: string;
    sublabel: string;
    accentCls: string;
    borderCls: string;
    headline?: string;
    sub?: string;
    upside?: number;
    available: boolean;
    unavailMsg?: string;
  }

  const cards: ModelCard[] = [
    {
      key: "dcf",
      label: "DCF",
      sublabel: "Discounted Cash Flow",
      accentCls: "text-blue-400",
      borderCls: "hover:border-blue-700/60",
      headline: dcf?.intrinsic_value != null ? fmtUsd(dcf.intrinsic_value) : undefined,
      sub: dcf?.intrinsic_value != null ? "Intrinsic value / share" : undefined,
      upside: dcf?.upside_pct,
      available: dcf?.intrinsic_value != null,
      unavailMsg: dcf?.skipped ?? dcf?.error,
    },
    {
      key: "ddm",
      label: "DDM",
      sublabel: "Gordon Growth Model",
      accentCls: "text-purple-400",
      borderCls: "hover:border-purple-700/60",
      headline: ddm?.intrinsic_value != null ? fmtUsd(ddm.intrinsic_value) : undefined,
      sub: ddm?.intrinsic_value != null ? "Intrinsic value / share" : undefined,
      upside: ddm?.upside_pct,
      available: ddm?.intrinsic_value != null,
      unavailMsg: ddm?.skipped ?? ddm?.error,
    },
    {
      key: "monte_carlo",
      label: "Monte Carlo",
      sublabel: "1 000 Simulations · 1yr",
      accentCls: "text-amber-400",
      borderCls: "hover:border-amber-700/60",
      headline: mc?.mean != null ? fmtUsd(mc.mean) : undefined,
      sub: mc?.mean != null ? `${mc.prob_above_pct}% prob above current` : undefined,
      upside: mc?.mean != null && price ? (mc.mean - price) / price * 100 : undefined,
      available: mc?.mean != null,
      unavailMsg: mc?.skipped ?? mc?.error,
    },
    {
      key: "comps",
      label: "Comps",
      sublabel: comp?.sector ? `${comp.sector} sector` : "Sector Multiples",
      accentCls: "text-cyan-400",
      borderCls: "hover:border-cyan-700/60",
      headline: comp?.comparisons?.pe?.implied_price != null ? fmtUsd(comp.comparisons.pe.implied_price) : undefined,
      sub: comp?.comparisons?.pe ? "Implied by P/E comp" : undefined,
      upside: comp?.comparisons?.pe?.upside_pct,
      available: (comp?.comparisons && Object.keys(comp.comparisons).length > 0) ?? false,
      unavailMsg: comp?.error,
    },
    {
      key: "sensitivity",
      label: "Sensitivity",
      sublabel: "EPS × P/E Grid",
      accentCls: "text-rose-400",
      borderCls: "hover:border-rose-700/60",
      headline: sens?.current_eps != null ? `EPS $${sens.current_eps}` : undefined,
      sub: sens?.current_eps != null ? `${(sens.growth_scenarios?.length ?? 0)} growth × ${(sens.pe_scenarios?.length ?? 0)} P/E scenarios` : undefined,
      upside: undefined,
      available: sens?.table != null,
      unavailMsg: sens?.skipped ?? sens?.error,
    },
  ];

  return (
    <>
      {/* Active modal */}
      {open === "dcf" && dcf?.intrinsic_value != null && <DCFModal dcf={dcf} onClose={() => setOpen(null)} />}
      {open === "ddm" && ddm?.intrinsic_value != null && <DDMModal ddm={ddm} onClose={() => setOpen(null)} />}
      {open === "monte_carlo" && mc?.mean != null && <MonteCarloModal mc={mc} price={price} onClose={() => setOpen(null)} />}
      {open === "comps" && comp && <CompsModal comps={comp} onClose={() => setOpen(null)} />}
      {open === "sensitivity" && sens?.table != null && <SensitivityModal sens={sens} onClose={() => setOpen(null)} />}

      <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-4">
        <h2 className="font-bold text-sm uppercase tracking-wide text-gray-300">
          Quantitative Valuation Models
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {cards.map((c) => (
            <button
              key={c.key}
              onClick={() => c.available ? setOpen(c.key) : undefined}
              className={`text-left bg-gray-800/50 rounded-xl p-4 border border-gray-700/50 transition-all group ${
                c.available
                  ? `cursor-pointer ${c.borderCls} hover:bg-gray-800`
                  : "cursor-default opacity-50"
              }`}
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <p className={`text-xs font-bold uppercase tracking-widest ${c.accentCls}`}>{c.label}</p>
                  <p className="text-[10px] text-gray-500 mt-0.5">{c.sublabel}</p>
                </div>
                {c.available && (
                  <span className="text-gray-600 group-hover:text-gray-400 text-xs transition-colors">→</span>
                )}
              </div>

              {c.available && c.headline ? (
                <div className="mt-3">
                  <p className="text-lg font-bold font-mono text-gray-100">{c.headline}</p>
                  {c.sub && <p className="text-[10px] text-gray-500 mt-0.5">{c.sub}</p>}
                  {c.upside != null && (
                    <p className={`text-sm font-bold font-mono mt-1 ${upColor(c.upside)}`}>
                      {fmtPct(c.upside)} implied upside
                    </p>
                  )}
                </div>
              ) : (
                <p className="text-[10px] text-gray-600 mt-3 italic leading-relaxed">{c.unavailMsg ?? "N/A"}</p>
              )}

              {c.available && (
                <p className={`text-[10px] mt-3 ${c.accentCls} opacity-70 group-hover:opacity-100 transition-opacity`}>
                  Click to view full model →
                </p>
              )}
            </button>
          ))}
        </div>
      </div>
    </>
  );
};

// ─── Signal colour helper (used in technical preview card) ───────────────────────

const SIG_TEXT: Record<string, string> = {
  STRONG_BUY: "text-green-300",
  BUY_NOW: "text-green-400",
  WAIT: "text-yellow-300",
  SELL_NOW: "text-red-400",
  STRONG_SELL: "text-red-300",
};


// ─── Component ───────────────────────────────────────────────────────────────────

const ResearchReport: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAppSelector((s) => s.auth);
  const isHe = user?.preferred_language === "he";

  const [rec, setRec] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(true);
  const [tradeModal, setTradeModal] = useState<{ type: OrderType } | null>(null);

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        const data = await recommendationsApi.getRecommendation(Number(id));
        setRec(data);
      } catch {
        navigate("/recommendations");
      }
      setLoading(false);
    })();
  }, [id]);

  const handleConfirmTrade = async (quantity: number, price: number) => {
    if (!rec || !tradeModal) return;
    try {
      await ordersApi.createOrder({
        symbol: rec.symbol,
        order_type: tradeModal.type,
        quantity,
        price,
        recommendation_id: rec.id,
      });
      await recommendationsApi.acknowledgeRecommendation(rec.id);
      setTradeModal(null);
      navigate("/orders");
    } catch (e: any) {
      alert(e.response?.data?.detail || "Order failed");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500" />
      </div>
    );
  }

  if (!rec) return null;

  const fa = rec.fundamental_analysis;
  const isShort = rec.recommendation_type === RecommendationType.SELL || rec.recommendation_type === RecommendationType.STRONG_SELL;
  // Infer direction from recommendation type when direction_bias is absent or NEUTRAL
  const rawBias = fa?.direction_bias;
  const bias = rawBias && rawBias !== "NEUTRAL"
    ? rawBias
    : isShort ? "SHORT" : "LONG";
  const currentPrice = rec.current_price_at_recommendation;

  const returnPct = rec.expected_return_pct ?? fa?.expected_return_pct;
  const returnPositive = (returnPct || 0) >= 0;

  const triggerBadgeText = () => {
    if (rec.trigger_type === "PRICE_ALERT") return { text: isHe ? "תנועת מחיר" : "Price Alert", cls: "bg-orange-900/30 text-orange-300" };
    if (rec.trigger_type === "NEWS_ALERT") return { text: isHe ? "חדשות" : "News Alert", cls: "bg-purple-900/30 text-purple-300" };
    if (rec.trigger_type === "EARNINGS") return { text: isHe ? "דוח רבעוני" : "Earnings", cls: "bg-blue-900/30 text-blue-300" };
    return null;
  };
  const trigger = triggerBadgeText();

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="max-w-4xl mx-auto space-y-6">
      {/* Back */}
      <Link to="/recommendations" className="text-sm text-gray-400 hover:text-gray-200 flex items-center gap-1">
        ← {isHe ? "חזור להמלצות" : "Back to Recommendations"}
      </Link>

      {/* Hero Header */}
      <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 flex-wrap mb-2">
              <h1 className="text-3xl font-bold font-mono">{rec.symbol}</h1>
              <span className={`px-3 py-1 rounded-lg text-sm font-bold border ${recColor(rec.recommendation_type)}`}>
                {rec.recommendation_type.replace("_", " ")}
              </span>
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${directionBadge(bias)}`}>
                {bias}
              </span>
              {trigger && (
                <span className={`px-2 py-0.5 rounded text-xs ${trigger.cls}`}>{trigger.text}</span>
              )}
            </div>
            {rec.asset_name && <p className="text-gray-400 text-sm">{rec.asset_name}</p>}
            {rec.sector && <p className="text-xs text-gray-500 mt-0.5">{rec.sector}</p>}
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-500">{isHe ? "מחיר בעת ניתוח" : "Price at analysis"}</p>
            <p className="text-2xl font-bold">{currentPrice ? `$${currentPrice.toFixed(2)}` : "—"}</p>
            <p className="text-xs text-gray-500 mt-1">
              {new Date(rec.created_at).toLocaleString(isHe ? "he-IL" : "en-US")}
            </p>
          </div>
        </div>

        {/* Key Numbers Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
          <div>
            <p className="text-xs text-gray-500">{isHe ? "ביטחון" : "Confidence"}</p>
            <ScoreBar value={rec.confidence_score} color={isShort ? "bg-red-500" : "bg-green-500"} />
            <p className="text-sm font-bold mt-0.5">{rec.confidence_score.toFixed(0)}%</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">{isShort ? (isHe ? "יעד שורט" : "Short Target") : (isHe ? "מחיר יעד" : "Target Price")}</p>
            <p className="text-sm font-bold">{rec.target_price ? `$${rec.target_price.toFixed(2)}` : "—"}</p>
            {currentPrice && rec.target_price && (
              <p className={`text-xs ${isShort ? "text-red-400" : "text-green-400"}`}>
                {(((rec.target_price - currentPrice) / currentPrice) * 100).toFixed(1)}%
              </p>
            )}
          </div>
          <div>
            <p className="text-xs text-gray-500">{isHe ? "סטופ לוס" : "Stop Loss"}</p>
            <p className="text-sm font-bold">{rec.stop_loss ? `$${rec.stop_loss.toFixed(2)}` : "—"}</p>
            {currentPrice && rec.stop_loss && (
              <p className="text-xs text-gray-400">
                {(((rec.stop_loss - currentPrice) / currentPrice) * 100).toFixed(1)}%
              </p>
            )}
          </div>
          <div>
            <p className="text-xs text-gray-500">{isHe ? "תשואה צפויה" : "Expected Return"}</p>
            <p className={`text-sm font-bold ${returnPositive ? "text-green-400" : "text-red-400"}`}>
              {returnPct != null ? `${returnPct >= 0 ? "+" : ""}${returnPct.toFixed(1)}%` : "—"}
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-3 mt-6">
          {!isShort ? (
            <button
              onClick={() => setTradeModal({ type: OrderType.BUY })}
              className="flex-1 bg-green-600 hover:bg-green-700 text-white rounded-xl py-3 font-medium"
            >
              {isHe ? "פתח פוזיציית LONG" : "Open LONG Position"}
            </button>
          ) : (
            <button
              onClick={() => setTradeModal({ type: OrderType.SELL })}
              className="flex-1 bg-red-600 hover:bg-red-700 text-white rounded-xl py-3 font-medium"
            >
              {isHe ? "פתח פוזיציית SHORT" : "Open SHORT Position"}
            </button>
          )}
          <Link
            to={`/technical/${rec.id}`}
            className="flex-1 border border-blue-700 text-blue-400 hover:text-blue-300 rounded-xl py-3 text-sm font-medium text-center transition-colors"
          >
            {isHe ? "ניתוח טכני ←" : "Technical Analysis →"}
          </Link>
        </div>
      </div>

      {/* Investment Thesis */}
      {fa?.thesis && (
        <div className={`rounded-2xl p-6 border ${isShort ? "bg-red-950/20 border-red-900/30" : "bg-green-950/20 border-green-900/30"}`}>
          <h2 className="font-bold text-sm uppercase tracking-wide mb-3 text-gray-400">
            {isHe ? "תזה להשקעה" : "Investment Thesis"}
          </h2>
          <p className="text-gray-200 leading-relaxed">{fa.thesis}</p>
        </div>
      )}

      {/* Short Catalysts */}
      {isShort && fa?.short_catalysts && fa.short_catalysts.length > 0 && (
        <div className="bg-red-950/20 rounded-2xl p-6 border border-red-900/30">
          <h2 className="font-bold text-sm uppercase tracking-wide mb-3 text-red-400">
            {isHe ? "קטליזטורים לירידה" : "Downside Catalysts"}
          </h2>
          <ul className="space-y-2">
            {fa.short_catalysts.map((c, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                <span className="text-red-400 mt-0.5">▼</span>
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Fundamental Analysis */}
      {fa && (
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-5">
          <h2 className="font-bold">{isHe ? "ניתוח בסיסי — הפקיד" : "Fundamental Analysis"}</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Assessment Badges */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">{isHe ? "הערכת שווי" : "Valuation"}</span>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  fa.valuation_assessment === "UNDERVALUED" ? "bg-green-900/40 text-green-400" :
                  fa.valuation_assessment === "OVERVALUED" ? "bg-red-900/40 text-red-400" :
                  "bg-gray-800 text-gray-400"
                }`}>
                  {fa.valuation_assessment}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">{isHe ? "בריאות פיננסית" : "Financial Health"}</span>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  fa.financial_health === "EXCELLENT" || fa.financial_health === "GOOD" ? "bg-green-900/40 text-green-400" :
                  fa.financial_health === "POOR" ? "bg-red-900/40 text-red-400" :
                  "bg-yellow-900/40 text-yellow-400"
                }`}>
                  {fa.financial_health}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">{isHe ? "אופק השקעה" : "Horizon"}</span>
                <span className="text-xs text-gray-300 bg-gray-800 px-2 py-0.5 rounded">
                  {fa.investment_horizon?.replace("_", " ")}
                </span>
              </div>
            </div>

            {/* Key Metrics */}
            {fa.key_metrics_summary && (
              <div className="space-y-1.5 text-xs text-gray-300">
                {Object.entries(fa.key_metrics_summary).map(([k, v]) => v && (
                  <div key={k}>
                    <span className="text-gray-500">{k.replace(/_/g, " ")}: </span>
                    {v as string}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Bull / Bear */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-green-950/20 rounded-xl p-4 border border-green-900/20">
              <p className="text-xs font-bold text-green-400 mb-2">{isHe ? "תרחיש חיובי" : "Bull Case"}</p>
              <p className="text-sm text-gray-300">{fa.bull_case}</p>
            </div>
            <div className="bg-red-950/20 rounded-xl p-4 border border-red-900/20">
              <p className="text-xs font-bold text-red-400 mb-2">{isHe ? "תרחיש שלילי" : "Bear Case"}</p>
              <p className="text-sm text-gray-300">{fa.bear_case}</p>
            </div>
          </div>

          {/* Catalysts & Risk Factors */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {fa.catalysts && fa.catalysts.length > 0 && (
              <div>
                <p className="text-xs font-bold text-gray-400 mb-2">{isHe ? "קטליזטורים חיוביים" : "Positive Catalysts"}</p>
                <ul className="space-y-1">
                  {fa.catalysts.map((c, i) => (
                    <li key={i} className="text-xs text-gray-300 flex items-start gap-1.5">
                      <span className="text-green-400 mt-0.5">+</span>{c}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {fa.risk_factors && fa.risk_factors.length > 0 && (
              <div>
                <p className="text-xs font-bold text-gray-400 mb-2">{isHe ? "גורמי סיכון" : "Risk Factors"}</p>
                <ul className="space-y-1">
                  {fa.risk_factors.map((r, i) => (
                    <li key={i} className="text-xs text-gray-300 flex items-start gap-1.5">
                      <span className="text-red-400 mt-0.5">!</span>{r}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Analyst Notes */}
          {fa.analyst_notes && (
            <div>
              <p className="text-xs font-bold text-gray-400 mb-2">{isHe ? "הערות אנליסט" : "Analyst Notes"}</p>
              <p className="text-sm text-gray-300 leading-relaxed">{fa.analyst_notes}</p>
            </div>
          )}

          {fa.sector_comparison && (
            <div>
              <p className="text-xs font-bold text-gray-400 mb-1">{isHe ? "השוואה לסקטור" : "Sector Comparison"}</p>
              <p className="text-sm text-gray-300">{fa.sector_comparison}</p>
            </div>
          )}
        </div>
      )}

      {/* Quantitative Models */}
      {fa?.quantitative_models && (
        <QuantModels qm={fa.quantitative_models} price={currentPrice ?? undefined} />
      )}

      {/* Senior Committee Decision */}
      {(rec.senior_notes || rec.senior_review_notes) && (
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <h2 className="font-bold mb-3">{isHe ? "ועדת הבכיר — החלטה סופית" : "Senior Committee — Final Decision"}</h2>
          {rec.senior_review_notes && (
            <div className="mb-3">
              <p className="text-xs text-gray-500 mb-1">{isHe ? "אישור" : "Approval Reasoning"}</p>
              <p className="text-sm text-gray-300">{rec.senior_review_notes}</p>
            </div>
          )}
          {rec.senior_notes && (
            <div>
              <p className="text-xs text-gray-500 mb-1">{isHe ? "הערות ועדה" : "Committee Notes"}</p>
              <p className="text-sm text-gray-300">{rec.senior_notes}</p>
            </div>
          )}
        </div>
      )}

      {/* Technical Analysis — Preview Card */}
      <Link
        to={`/technical/${rec.id}`}
        className="block bg-gray-900 rounded-2xl border border-gray-800 hover:border-blue-700/50 transition-colors overflow-hidden group"
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800 bg-gray-900/80">
          <span className="text-xs text-gray-500 tracking-widest font-mono">TECHNICAL ANALYSIS</span>
          <span className="text-xs text-blue-500 group-hover:text-blue-400 font-mono tracking-wider">
            {isHe ? "פתח טרמינל ←" : "OPEN TERMINAL →"}
          </span>
        </div>
        {rec.technical_analysis ? (
          <div dir="ltr" className="px-5 py-4 flex items-center gap-6 font-mono">
            <div>
              <p className={`text-xl font-black tracking-widest ${SIG_TEXT[rec.technical_analysis.timing_signal] ?? "text-yellow-300"}`}>
                {rec.technical_analysis.timing_signal?.replace("_", " ")}
              </p>
              <p className="text-xs text-gray-600 mt-0.5">{rec.technical_analysis.signal_strength}</p>
            </div>
            <div className="flex-1 bg-gray-800 rounded-full h-1.5">
              <div
                className={`h-1.5 rounded-full ${
                  (rec.technical_analysis.technical_score ?? 50) >= 60 ? "bg-green-500" :
                  (rec.technical_analysis.technical_score ?? 50) <= 40 ? "bg-red-500" : "bg-yellow-500"
                }`}
                style={{ width: `${rec.technical_analysis.technical_score ?? 50}%` }}
              />
            </div>
            <span className="text-sm text-gray-300 w-12 text-right">
              {(rec.technical_analysis.technical_score ?? 50).toFixed(0)}/100
            </span>
          </div>
        ) : (
          <div className="px-5 py-6 flex flex-col items-center gap-2">
            <p className="text-gray-500 text-sm">{isHe ? "ניתוח טכני טרם בוצע — לחץ להרצה" : "Technical analysis not yet run — click to open"}</p>
          </div>
        )}
      </Link>

      {/* Trade Modal */}
      {tradeModal && rec && (
        <ConfirmTradeModal
          recommendation={rec}
          orderType={tradeModal.type}
          isHe={isHe}
          onConfirm={handleConfirmTrade}
          onCancel={() => setTradeModal(null)}
        />
      )}
    </div>
  );
};

export default ResearchReport;
