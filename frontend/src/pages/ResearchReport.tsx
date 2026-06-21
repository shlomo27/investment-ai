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

const Chip: React.FC<{ label: string; value: React.ReactNode; cls?: string }> = ({ label, value, cls }) => (
  <div className="bg-gray-800/60 rounded-xl p-3 flex flex-col gap-0.5">
    <p className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</p>
    <p className={`text-sm font-bold font-mono ${cls ?? "text-gray-200"}`}>{value}</p>
  </div>
);

const ModelSkipBadge: React.FC<{ msg?: string }> = ({ msg }) => (
  <p className="text-xs text-gray-500 italic py-1">{msg ?? "Not available"}</p>
);

const QuantModels: React.FC<{ qm: QuantitativeModels; price?: number }> = ({ qm, price }) => {
  const dcf  = qm.dcf;
  const ddm  = qm.ddm;
  const mc   = qm.monte_carlo;
  const sens = qm.sensitivity;
  const comp = qm.comps;

  const hasDcf  = dcf?.intrinsic_value != null;
  const hasDdm  = ddm?.intrinsic_value != null;
  const hasMc   = mc?.mean != null;
  const hasSens = sens?.table != null;
  const hasComp = comp?.comparisons && Object.keys(comp.comparisons).length > 0;

  const anyModel = hasDcf || hasDdm || hasMc || hasSens || hasComp;
  if (!anyModel) return null;

  return (
    <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-6">
      <h2 className="font-bold text-sm uppercase tracking-wide text-gray-300">
        Quantitative Valuation Models
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

        {/* DCF */}
        <div className="space-y-3">
          <p className="text-xs font-bold text-blue-400 uppercase tracking-widest">
            DCF — Discounted Cash Flow
          </p>
          {hasDcf ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                <Chip label="Intrinsic Value" value={fmtUsd(dcf!.intrinsic_value)} />
                <Chip
                  label="Upside vs Current"
                  value={fmtPct(dcf!.upside_pct)}
                  cls={upColor(dcf!.upside_pct)}
                />
                <Chip label="WACC" value={`${dcf!.wacc_pct}%`} />
                <Chip label="FCF Growth Assumed" value={`${dcf!.fcf_growth_pct}%`} />
                <Chip label="Terminal Growth" value={`${dcf!.terminal_growth_pct}%`} />
                <Chip label="PV 5-yr FCF" value={`$${Number(dcf!.pv_5yr_fcf).toLocaleString()}`} />
              </div>
            </>
          ) : (
            <ModelSkipBadge msg={dcf?.skipped ?? dcf?.error} />
          )}
        </div>

        {/* DDM */}
        <div className="space-y-3">
          <p className="text-xs font-bold text-purple-400 uppercase tracking-widest">
            DDM — Gordon Growth Model
          </p>
          {hasDdm ? (
            <div className="grid grid-cols-2 gap-2">
              <Chip label="Intrinsic Value" value={fmtUsd(ddm!.intrinsic_value)} />
              <Chip
                label="Upside vs Current"
                value={fmtPct(ddm!.upside_pct)}
                cls={upColor(ddm!.upside_pct)}
              />
              <Chip label="Div / Share" value={fmtUsd(ddm!.dividend_per_share)} />
              <Chip label="Sustainable Growth" value={`${ddm!.growth_rate_pct}%`} />
              <Chip label="Cost of Equity" value={`${ddm!.cost_of_equity_pct}%`} />
            </div>
          ) : (
            <ModelSkipBadge msg={ddm?.skipped ?? ddm?.error} />
          )}
        </div>

        {/* Monte Carlo */}
        <div className="space-y-3">
          <p className="text-xs font-bold text-amber-400 uppercase tracking-widest">
            Monte Carlo — 1 000 Simulations · 1-Year
          </p>
          {hasMc ? (
            <>
              <div className="grid grid-cols-3 gap-2">
                <Chip label="P10 (Bear)" value={fmtUsd(mc!.p10)} cls="text-red-400" />
                <Chip label="P25" value={fmtUsd(mc!.p25)} cls="text-orange-400" />
                <Chip label="Mean" value={fmtUsd(mc!.mean)} />
                <Chip label="P75" value={fmtUsd(mc!.p75)} cls="text-lime-400" />
                <Chip label="P90 (Bull)" value={fmtUsd(mc!.p90)} cls="text-green-400" />
                <Chip
                  label="Prob > Current"
                  value={`${mc!.prob_above_pct}%`}
                  cls={upColor((mc!.prob_above_pct ?? 50) - 50)}
                />
              </div>
              <p className="text-[10px] text-gray-600 font-mono">
                vol {mc!.annual_vol_pct}%/yr · drift {mc!.annual_drift_pct}%/yr · {mc!.simulations} paths · GBM
              </p>
              {/* Distribution bar */}
              <div className="relative h-5 bg-gray-800 rounded-full overflow-hidden mt-1">
                {price && mc && mc.p10 && mc.p90 && (() => {
                  const lo = mc.p10 * 0.95, hi = mc.p90 * 1.05, range = hi - lo;
                  const pct = (v: number) => `${Math.max(0, Math.min(100, (v - lo) / range * 100)).toFixed(1)}%`;
                  return (
                    <>
                      <div className="absolute inset-y-0 bg-gradient-to-r from-red-900/50 via-amber-700/40 to-green-900/50 rounded-full"
                        style={{ left: pct(mc.p10!), right: `${100 - parseFloat(pct(mc.p90!))}%` }} />
                      <div className="absolute inset-y-0 w-0.5 bg-white/60" style={{ left: pct(price) }} />
                    </>
                  );
                })()}
              </div>
              <div className="flex justify-between text-[9px] text-gray-600 font-mono">
                <span>P10 {fmtUsd(mc!.p10)}</span>
                {price && <span className="text-white/50">▲ current {fmtUsd(price)}</span>}
                <span>P90 {fmtUsd(mc!.p90)}</span>
              </div>
            </>
          ) : (
            <ModelSkipBadge msg={mc?.skipped ?? mc?.error} />
          )}
        </div>

        {/* Comps */}
        <div className="space-y-3">
          <p className="text-xs font-bold text-cyan-400 uppercase tracking-widest">
            Comps — Sector Comparable Multiples
            {comp?.sector && <span className="ml-2 normal-case font-normal text-gray-500">({comp.sector})</span>}
          </p>
          {hasComp ? (
            <div className="space-y-2">
              {(["pe", "pb", "ps"] as const).map((key) => {
                const m = comp!.comparisons![key];
                if (!m) return null;
                const labelMap = { pe: "P/E", pb: "P/B", ps: "P/S" };
                return (
                  <div key={key} className="bg-gray-800/60 rounded-xl p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-gray-400 font-mono">{labelMap[key]}</span>
                      <span className={`text-xs font-bold ${m.premium_pct >= 0 ? "text-red-400" : "text-green-400"}`}>
                        {m.premium_pct >= 0 ? "+" : ""}{m.premium_pct.toFixed(1)}% vs sector
                      </span>
                    </div>
                    <div className="flex items-center gap-4 text-xs font-mono">
                      <span>Co: <span className="text-gray-200">{m.company}x</span></span>
                      <span>Sect: <span className="text-gray-400">{m.sector_avg}x</span></span>
                      <span className="ml-auto">
                        Implied <span className={upColor(m.upside_pct)}>{fmtUsd(m.implied_price)}</span>
                        <span className={`ml-1 ${upColor(m.upside_pct)}`}>({fmtPct(m.upside_pct)})</span>
                      </span>
                    </div>
                  </div>
                );
              })}
              {comp?.sector_averages && (
                <p className="text-[10px] text-gray-600 font-mono pt-1">
                  Sector avg: P/E {comp.sector_averages.pe}x · P/B {comp.sector_averages.pb}x · P/S {comp.sector_averages.ps}x · EV/EBITDA {comp.sector_averages.ev_ebitda}x
                </p>
              )}
            </div>
          ) : (
            <ModelSkipBadge msg={comp?.error} />
          )}
        </div>
      </div>

      {/* Sensitivity Table */}
      {hasSens && sens!.table && (
        <div className="space-y-3">
          <p className="text-xs font-bold text-rose-400 uppercase tracking-widest">
            Sensitivity Analysis — EPS ${sens!.current_eps} × P/E Multiple
            <span className="ml-2 normal-case font-normal text-gray-500">
              (current: P/E {sens!.current_pe}x @ {fmtUsd(sens!.current_price)})
            </span>
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono border-collapse">
              <thead>
                <tr>
                  <th className="text-left text-gray-500 pb-2 pr-3">EPS Growth →</th>
                  {sens!.pe_scenarios?.map((pe) => (
                    <th key={pe} className="text-center text-gray-500 pb-2 px-2">P/E {pe}x</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sens!.growth_scenarios?.map((g) => {
                  const row = sens!.table![g];
                  if (!row) return null;
                  return (
                    <tr key={g} className="border-t border-gray-800/60">
                      <td className="pr-3 py-1.5 text-gray-400">{g}</td>
                      {sens!.pe_scenarios?.map((pe) => {
                        const v = row[String(pe)];
                        const current = sens!.current_price ?? 0;
                        const diff = current > 0 ? (v - current) / current : 0;
                        return (
                          <td key={pe} className={`text-center py-1.5 px-2 ${
                            diff > 0.15 ? "text-green-400 bg-green-900/10" :
                            diff > 0 ? "text-green-600" :
                            diff < -0.15 ? "text-red-400 bg-red-900/10" :
                            diff < 0 ? "text-red-600" : "text-gray-400"
                          }`}>
                            ${v.toFixed(0)}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] text-gray-600">
            Cells show implied share price. Green = above current price, red = below. Current: {fmtUsd(sens!.current_price)}
          </p>
        </div>
      )}
    </div>
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
