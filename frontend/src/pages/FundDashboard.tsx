import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../store";
import { fetchPortfolioSummary, fetchPortfolioRisk } from "../store/slices/portfolioSlice";
import { fetchRecommendations } from "../store/slices/notificationsSlice";
import { marketApi } from "../api/client";
import { UniverseStats, RecommendationType } from "../types";

const FundDashboard: React.FC = () => {
  const dispatch = useAppDispatch();
  const { summary } = useAppSelector((s) => s.portfolio);
  const { recommendations } = useAppSelector((s) => s.notifications);
  const { user } = useAppSelector((s) => s.auth);
  const isHe = user?.preferred_language === "he";

  const [universeStats, setUniverseStats] = useState<UniverseStats | null>(null);
  const [screenerRunning, setScreenerRunning] = useState(false);
  const [screenerResult, setScreenerResult] = useState<any>(null);
  const [universeLoading, setUniverseLoading] = useState(false);
  const [universeResult, setUniverseResult] = useState<any>(null);
  const [scanRunning, setScanRunning] = useState(false);
  const [scanResult, setScanResult] = useState<any>(null);
  const [scanStatus, setScanStatus] = useState<any>(null);

  useEffect(() => {
    dispatch(fetchPortfolioSummary());
    dispatch(fetchPortfolioRisk());
    dispatch(fetchRecommendations({}));
    loadUniverseStats();
  }, [dispatch]);

  const loadUniverseStats = async () => {
    try {
      const stats = await marketApi.getUniverseStats();
      setUniverseStats(stats);
    } catch {}
  };

  const handleRunScreener = async () => {
    setScreenerRunning(true);
    setScreenerResult(null);
    try {
      const result = await marketApi.runScreener();
      setScreenerResult(result);
      await loadUniverseStats();
    } catch (e: any) {
      setScreenerResult({ error: e?.response?.data?.detail || "Failed" });
    }
    setScreenerRunning(false);
  };

  const handleLoadUniverse = async () => {
    setUniverseLoading(true);
    setUniverseResult(null);
    try {
      const result = await marketApi.loadUniverse();
      setUniverseResult(result);
      await loadUniverseStats();
    } catch (e: any) {
      setUniverseResult({ error: e?.response?.data?.detail || "Failed" });
    }
    setUniverseLoading(false);
  };

  const handleScanNow = async () => {
    setScanRunning(true);
    setScanResult(null);
    setScanStatus(null);
    try {
      // Start scan — returns immediately (runs in background on server)
      const startResult = await marketApi.scanPoolNow();
      if (!startResult.started) {
        setScanResult({ error: startResult.error || startResult.message });
        setScanRunning(false);
        return;
      }

      // Poll /scan-status every 4 seconds until done
      const poll = async () => {
        try {
          const status = await marketApi.getScanStatus();
          setScanStatus(status);
          if (status.running) {
            setTimeout(poll, 4000);
          } else {
            setScanResult({ done: true });
            setScanRunning(false);
            dispatch(fetchRecommendations({}));
          }
        } catch {
          setScanResult({ error: "Lost connection to server — check results page" });
          setScanRunning(false);
        }
      };
      setTimeout(poll, 3000); // first poll after 3s
    } catch (e: any) {
      setScanResult({ error: e?.response?.data?.detail || "Failed to start scan" });
      setScanRunning(false);
    }
  };

  const fmt = (v: number, prefix = "$") =>
    `${prefix}${Math.abs(v).toLocaleString("en", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;

  const fmtPct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;

  // Compute approved recommendation breakdown
  const approvedRecs = recommendations.filter((r) => r.status === "APPROVED" || r.status === "PRESENTED_TO_USER");
  const longRecs = approvedRecs.filter(
    (r) => r.recommendation_type === RecommendationType.BUY || r.recommendation_type === RecommendationType.STRONG_BUY
  );
  const shortRecs = approvedRecs.filter(
    (r) => r.recommendation_type === RecommendationType.SELL || r.recommendation_type === RecommendationType.STRONG_SELL
  );

  // Portfolio long vs short exposure from holdings
  const positions = summary?.positions || [];
  const longValue = positions.reduce((s, p) => s + p.current_value, 0);
  const grossExposure = longValue; // currently only long positions tracked
  const netExposure = longValue;

  const totalPnl = summary?.total_pnl || 0;
  const totalPnlPct = summary?.total_pnl_pct || 0;
  const pnlPositive = totalPnl >= 0;

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{isHe ? "לוח בקרה - קרן גידור" : "Fund Dashboard"}</h1>
          <p className="text-gray-400 text-sm mt-1">
            {isHe ? "תצוגה מקצועית של הקרן — Long/Short Equity" : "Professional fund view — Long/Short Equity"}
          </p>
        </div>
        <Link to="/dashboard" className="text-sm text-gray-400 hover:text-gray-200">
          {isHe ? "← דשבורד רגיל" : "← Standard Dashboard"}
        </Link>
      </div>

      {/* P&L + Exposure Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
          <p className="text-xs text-gray-400 mb-1">{isHe ? "שווי תיק" : "Portfolio NAV"}</p>
          <p className="text-2xl font-bold">{fmt(summary?.total_value || 0)}</p>
        </div>
        <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
          <p className="text-xs text-gray-400 mb-1">{isHe ? "רווח/הפסד כולל" : "Total P&L"}</p>
          <p className={`text-2xl font-bold ${pnlPositive ? "text-green-400" : "text-red-400"}`}>
            {fmtPct(totalPnlPct)}
          </p>
          <p className={`text-sm ${pnlPositive ? "text-green-400" : "text-red-400"}`}>
            {pnlPositive ? "+" : ""}{fmt(totalPnl)}
          </p>
        </div>
        <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
          <p className="text-xs text-gray-400 mb-1">{isHe ? "חשיפה ברוטו (Long)" : "Gross Exposure (Long)"}</p>
          <p className="text-2xl font-bold text-green-400">{fmt(grossExposure)}</p>
          <p className="text-xs text-gray-500">{positions.length} {isHe ? "פוזיציות" : "positions"}</p>
        </div>
        <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
          <p className="text-xs text-gray-400 mb-1">{isHe ? "מזומן פנוי" : "Available Cash"}</p>
          <p className="text-2xl font-bold text-blue-400">{fmt(summary?.cash_balance || 0)}</p>
        </div>
      </div>

      {/* AI Signal Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-900 rounded-2xl p-5 border border-green-900/40">
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2.5 h-2.5 bg-green-400 rounded-full" />
            <p className="text-sm font-medium text-green-300">{isHe ? "המלצות LONG" : "LONG Signals"}</p>
          </div>
          <p className="text-3xl font-bold text-green-400">{longRecs.length}</p>
          <p className="text-xs text-gray-400 mt-1">{isHe ? "המלצות BUY/STRONG_BUY פעילות" : "Active BUY/STRONG_BUY"}</p>
          {longRecs.slice(0, 3).map((r) => (
            <Link
              key={r.id}
              to={`/research/${r.id}`}
              className="flex items-center justify-between mt-2 text-xs text-gray-300 hover:text-white"
            >
              <span className="font-mono font-bold">{r.symbol}</span>
              <span className="text-green-400">{r.confidence_score.toFixed(0)}%</span>
            </Link>
          ))}
        </div>
        <div className="bg-gray-900 rounded-2xl p-5 border border-red-900/40">
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2.5 h-2.5 bg-red-400 rounded-full" />
            <p className="text-sm font-medium text-red-300">{isHe ? "המלצות SHORT" : "SHORT Signals"}</p>
          </div>
          <p className="text-3xl font-bold text-red-400">{shortRecs.length}</p>
          <p className="text-xs text-gray-400 mt-1">{isHe ? "המלצות SELL/STRONG_SELL פעילות" : "Active SELL/STRONG_SELL"}</p>
          {shortRecs.slice(0, 3).map((r) => (
            <Link
              key={r.id}
              to={`/research/${r.id}`}
              className="flex items-center justify-between mt-2 text-xs text-gray-300 hover:text-white"
            >
              <span className="font-mono font-bold">{r.symbol}</span>
              <span className="text-red-400">{r.confidence_score.toFixed(0)}%</span>
            </Link>
          ))}
        </div>
        <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
          <p className="text-xs text-gray-400 mb-3">{isHe ? "יחס Long/Short" : "L/S Ratio"}</p>
          <p className="text-3xl font-bold text-white">
            {shortRecs.length > 0 ? (longRecs.length / shortRecs.length).toFixed(1) : "—"}
            <span className="text-base text-gray-400 ml-1">: 1</span>
          </p>
          <p className="text-xs text-gray-500 mt-1">{isHe ? "Long לכל Short" : "longs per short"}</p>
          <div className="mt-3 flex gap-2">
            <div className="flex-1 bg-green-900/30 rounded-lg p-2 text-center">
              <p className="text-xs text-gray-400">Long</p>
              <p className="font-bold text-green-400">{longRecs.length}</p>
            </div>
            <div className="flex-1 bg-red-900/30 rounded-lg p-2 text-center">
              <p className="text-xs text-gray-400">Short</p>
              <p className="font-bold text-red-400">{shortRecs.length}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Universe & Pre-Screener */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Universe Stats */}
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold">{isHe ? "יקום המניות" : "Stock Universe"}</h2>
            <button
              onClick={handleLoadUniverse}
              disabled={universeLoading}
              className="text-xs text-blue-400 hover:text-blue-300 disabled:text-gray-600"
            >
              {universeLoading ? (isHe ? "טוען..." : "Loading...") : (isHe ? "רענן יקום" : "Refresh Universe")}
            </button>
          </div>

          {universeStats ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-gray-800 rounded-xl p-3">
                  <p className="text-xs text-gray-400">{isHe ? "סה\"כ ביקום" : "In Universe"}</p>
                  <p className="text-xl font-bold text-white">{universeStats.universe_total.toLocaleString()}</p>
                  <p className="text-xs text-gray-500">S&P 500 + S&P 400</p>
                </div>
                <div className="bg-gray-800 rounded-xl p-3">
                  <p className="text-xs text-gray-400">{isHe ? "ביקום זרוע" : "Curated Pool"}</p>
                  <p className="text-xl font-bold text-white">{universeStats.seeded_pool.toLocaleString()}</p>
                  <p className="text-xs text-gray-500">{isHe ? "נבחרים ידנית" : "Hand-picked"}</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-green-900/20 border border-green-900/40 rounded-xl p-3">
                  <p className="text-xs text-green-400">{isHe ? "LONG פעיל" : "Active LONG"}</p>
                  <p className="text-xl font-bold text-green-400">{universeStats.active_long}</p>
                </div>
                <div className="bg-red-900/20 border border-red-900/40 rounded-xl p-3">
                  <p className="text-xs text-red-400">{isHe ? "SHORT פעיל" : "Active SHORT"}</p>
                  <p className="text-xl font-bold text-red-400">{universeStats.active_short}</p>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500 text-sm">
              {isHe ? "אין נתוני יקום — טען יקום תחילה" : "No universe data — load universe first"}
            </div>
          )}

          {universeResult && (
            <div className={`mt-3 p-3 rounded-xl text-xs ${universeResult.error ? "bg-red-900/20 text-red-400" : "bg-green-900/20 text-green-400"}`}>
              {universeResult.error
                ? universeResult.error
                : `${isHe ? "נוספו" : "Inserted"} ${universeResult.inserted} | ${isHe ? "קיים" : "Skipped"} ${universeResult.skipped}`}
            </div>
          )}
        </div>

        {/* Pre-Screener Control */}
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold">{isHe ? "פרה-סקרינר" : "Pre-Screener"}</h2>
            <button
              onClick={handleRunScreener}
              disabled={screenerRunning}
              className="text-xs bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white px-3 py-1.5 rounded-lg"
            >
              {screenerRunning ? (isHe ? "מריץ..." : "Running...") : (isHe ? "הרץ עכשיו" : "Run Now")}
            </button>
          </div>
          <p className="text-xs text-gray-400 mb-4">
            {isHe
              ? "מדרג את כל ~900 מניות ה-S&P500+S&P400 ובוחר 80 LONG + 20 SHORT לניתוח AI יומי. מניות שנותחו לאחרונה מקבלות קנס כדי להבטיח רוטציה — כיסוי מלא תוך ~9 ימים."
              : "Scores all ~900 S&P500+S&P400 stocks and selects 80 LONG + 20 SHORT for daily AI analysis. Recently-analyzed stocks are penalized to ensure rotation — full coverage in ~9 days."}
          </p>

          {universeStats && (universeStats.top_long.length > 0 || universeStats.top_short.length > 0) ? (
            <div className="space-y-2 mb-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide">
                {isHe ? "מועמדים LONG מובילים" : "Top LONG Candidates"}
              </p>
              {universeStats.top_long.slice(0, 5).map((c) => (
                <div key={c.symbol} className="flex items-center justify-between text-xs">
                  <span className="font-mono font-bold text-white">{c.symbol}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-20 bg-gray-800 rounded-full h-1.5">
                      <div className="bg-green-500 h-1.5 rounded-full" style={{ width: `${c.long_score}%` }} />
                    </div>
                    <span className="text-green-400 w-8 text-right">{c.long_score.toFixed(0)}</span>
                  </div>
                </div>
              ))}
              <p className="text-xs text-gray-500 uppercase tracking-wide mt-3">
                {isHe ? "מועמדים SHORT מובילים" : "Top SHORT Candidates"}
              </p>
              {universeStats.top_short.slice(0, 5).map((c) => (
                <div key={c.symbol} className="flex items-center justify-between text-xs">
                  <span className="font-mono font-bold text-white">{c.symbol}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-20 bg-gray-800 rounded-full h-1.5">
                      <div className="bg-red-500 h-1.5 rounded-full" style={{ width: `${c.short_score}%` }} />
                    </div>
                    <span className="text-red-400 w-8 text-right">{c.short_score.toFixed(0)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : universeStats ? (
            <div className="flex flex-col items-center justify-center py-6 text-center mb-4">
              <p className="text-2xl mb-2">📭</p>
              <p className="text-sm text-gray-400 font-medium">
                {isHe ? "הסקרינר טרם רץ" : "Screener hasn't run yet"}
              </p>
              <p className="text-xs text-gray-600 mt-1">
                {isHe ? "לחץ 'הרץ עכשיו' לבצע סינון ראשוני" : "Click 'Run Now' to score the universe"}
              </p>
            </div>
          ) : null}

          {screenerResult && (
            <div className={`p-3 rounded-xl text-xs ${screenerResult.error ? "bg-red-900/20 text-red-400" : "bg-blue-900/20 text-blue-300"}`}>
              {screenerResult.error ? screenerResult.error : (
                <span>
                  {isHe ? "דורגו" : "Scored"} {screenerResult.scored} |{" "}
                  <span className="text-green-400">Long {screenerResult.long_activated}</span> |{" "}
                  <span className="text-red-400">Short {screenerResult.short_activated}</span>
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* AI Full Scan Trigger */}
      <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <h2 className="font-bold mb-1">{isHe ? "סריקת AI מלאה" : "Run Full AI Scan"}</h2>
            <p className="text-xs text-gray-400 mb-2">
              {isHe
                ? "מריץ AI מלא על כל 100 המניות הפעילות היומיות (80 LONG + 20 SHORT) — 3 במקביל עד סיום. מחזור של 9 ימים לכיסוי כל ה-S&P500+S&P400."
                : "Runs full AI on all 100 active stocks (80 LONG + 20 SHORT) — 3 concurrent until done. 9-day cycle covers all S&P500+S&P400."}
            </p>
            <div className="flex items-center gap-2 text-xs text-gray-500 bg-gray-800/50 rounded-lg px-3 py-2 w-fit flex-wrap">
              <span className="text-blue-400">1.</span>
              <span>{isHe ? "רענן יקום" : "Refresh Universe"}</span>
              <span className="text-gray-700">→</span>
              <span className="text-blue-400">2.</span>
              <span>{isHe ? "הרץ סקרינר" : "Run Screener"}</span>
              <span className="text-gray-700">→</span>
              <span className="text-green-400">3.</span>
              <span className="text-green-400 font-medium">{isHe ? "סרוק עכשיו" : "Scan Now"}</span>
            </div>

            {/* Live progress during scan */}
            {scanRunning && scanStatus && scanStatus.scanned > 0 && (
              <div className="mt-3 p-3 rounded-xl bg-blue-900/20 border border-blue-900/30 text-xs text-blue-300 space-y-1">
                <p className="font-medium">
                  {isHe ? "סורק..." : "Scanning..."} ({scanStatus.scanned}/{scanStatus.total})
                </p>
                <p>
                  <span className="text-green-400">{isHe ? "אושרו" : "Approved"}: {scanStatus.approved}</span>{" "}|{" "}
                  <span className="text-red-400">{isHe ? "נדחו" : "Rejected"}: {scanStatus.rejected}</span>
                  {scanStatus.errors > 0 && <span className="text-yellow-400"> | {isHe ? "שגיאות" : "Errors"}: {scanStatus.errors}</span>}
                </p>
                {scanStatus.symbols_done?.length > 0 && (
                  <p className="font-mono text-gray-400 break-all">{scanStatus.symbols_done.slice(-10).join(", ")}</p>
                )}
              </div>
            )}

            {/* Final result */}
            {!scanRunning && scanResult?.done && scanStatus && (
              <div className="mt-3 p-3 rounded-xl bg-green-900/20 border border-green-900/30 text-xs text-green-300 space-y-1">
                <p className="font-medium text-green-400">✓ {isHe ? "הסריקה הושלמה!" : "Scan complete!"}</p>
                <p>
                  {isHe ? "נסרקו" : "Scanned"}: <strong>{scanStatus.scanned}</strong> |{" "}
                  <span className="text-green-400">{isHe ? "אושרו" : "Approved"}: {scanStatus.approved}</span> |{" "}
                  <span className="text-red-400">{isHe ? "נדחו" : "Rejected"}: {scanStatus.rejected}</span>
                </p>
              </div>
            )}

            {scanResult?.error && (
              <div className="mt-3 p-3 rounded-xl bg-red-900/20 text-red-400 text-xs">
                {scanResult.error}
              </div>
            )}

            {!scanRunning && !scanResult && (
              <p className="text-xs text-gray-600 mt-3">
                {isHe ? "הסריקה רצה אוטומטית כל יום ב-09:00 שעון ישראל" : "Scan runs automatically every day at 09:00 Israel time"}
              </p>
            )}

          </div>
          <button
            onClick={handleScanNow}
            disabled={scanRunning}
            className="shrink-0 flex items-center gap-2 bg-green-700 hover:bg-green-600 disabled:bg-gray-700 disabled:cursor-not-allowed text-white text-sm font-semibold px-5 py-3 rounded-xl transition-colors"
          >
            {scanRunning ? (
              <>
                <span className="animate-spin">⟳</span>
                {isHe ? "סורק..." : "Scanning..."}
              </>
            ) : (
              <>
                <span>⚡</span>
                {isHe ? "סרוק עכשיו" : "Scan Now"}
              </>
            )}
          </button>
        </div>
      </div>

      {/* Top Holdings with P&L */}
      <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-bold">{isHe ? "פוזיציות פעילות" : "Active Positions"}</h2>
          <Link to="/portfolio" className="text-xs text-blue-400 hover:text-blue-300">
            {isHe ? "פורטפוליו מלא" : "Full Portfolio"}
          </Link>
        </div>
        {positions.length === 0 ? (
          <p className="text-gray-500 text-sm text-center py-6">{isHe ? "אין פוזיציות" : "No positions"}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-gray-500 border-b border-gray-800">
                  <th className="text-left py-2">{isHe ? "מניה" : "Symbol"}</th>
                  <th className="text-right py-2">{isHe ? "כמות" : "Qty"}</th>
                  <th className="text-right py-2">{isHe ? "שווי" : "Value"}</th>
                  <th className="text-right py-2">{isHe ? "רווח/הפסד" : "P&L"}</th>
                  <th className="text-right py-2">{isHe ? "חשיפה" : "Exposure"}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/50">
                {positions.map((pos) => (
                  <tr key={pos.symbol} className="hover:bg-gray-800/30">
                    <td className="py-2.5 font-mono font-bold">{pos.symbol}</td>
                    <td className="py-2.5 text-right text-gray-300">{pos.quantity.toFixed(2)}</td>
                    <td className="py-2.5 text-right">{fmt(pos.current_value)}</td>
                    <td className={`py-2.5 text-right font-medium ${pos.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {fmtPct(pos.pnl_percentage)}
                    </td>
                    <td className="py-2.5 text-right text-gray-400">{pos.exposure_percentage.toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { to: "/recommendations", icon: "🎯", he: "המלצות AI", en: "AI Signals" },
          { to: "/portfolio", icon: "📊", he: "תיק השקעות", en: "Portfolio" },
          { to: "/watchlist", icon: "👁", he: "מעקב", en: "Watchlist" },
          { to: "/orders", icon: "📋", he: "עסקאות", en: "Trades" },
        ].map((a) => (
          <Link
            key={a.to}
            to={a.to}
            className="bg-gray-900 hover:bg-gray-800 border border-gray-800 rounded-2xl p-4 flex items-center gap-3 transition-colors"
          >
            <span className="text-2xl">{a.icon}</span>
            <span className="text-sm font-medium">{isHe ? a.he : a.en}</span>
          </Link>
        ))}
      </div>
    </div>
  );
};

export default FundDashboard;
