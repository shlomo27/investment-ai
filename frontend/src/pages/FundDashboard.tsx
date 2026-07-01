import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../store";
import { fetchPortfolioSummary, fetchPortfolioRisk } from "../store/slices/portfolioSlice";
import { fetchRecommendations } from "../store/slices/notificationsSlice";
import { marketApi } from "../api/client";
import { UniverseStats, RecommendationType } from "../types";
import PerformanceDashboard from "../components/Performance/PerformanceDashboard";
import RiskProfileModal from "../components/RiskProfileModal";
import EarningsCalendar from "../components/EarningsCalendar";
import SectorDashboard from "../components/SectorDashboard";
import StockComparison from "../components/StockComparison";
import PerformanceComparisonChart from "../components/Charts/PerformanceComparisonChart";
import PerformanceTimelineChart from "../components/Charts/PerformanceTimelineChart";

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
  const [earningsStatus, setEarningsStatus] = useState<any>(null);
  const [earningsChecking, setEarningsChecking] = useState(false);
  const [earningsCheckResult, setEarningsCheckResult] = useState<any>(null);

  // Dashboard tab state
  const [activeTab, setActiveTab] = useState<"fund" | "performance" | "sectors" | "earnings" | "compare">("fund");
  const [showRiskModal, setShowRiskModal] = useState(false);
  const [currentUser, setCurrentUser] = useState<any>(user);

  // Paper trading state
  const [paperStatus, setPaperStatus] = useState<any>(null);
  const [paperLoading, setPaperLoading] = useState(false);

  // Simulation state
  const [simSymbol, setSimSymbol] = useState("MU");
  const [simStep, setSimStep] = useState<Record<string, any>>({});
  const [simLoading, setSimLoading] = useState<Record<string, boolean>>({});

  useEffect(() => {
    dispatch(fetchPortfolioSummary());
    dispatch(fetchPortfolioRisk());
    dispatch(fetchRecommendations({}));
    loadUniverseStats();
    loadEarningsStatus();
    loadPaperStatus();
  }, [dispatch]);

  const loadUniverseStats = async () => {
    try {
      const stats = await marketApi.getUniverseStats();
      setUniverseStats(stats);
    } catch {}
  };

  const loadEarningsStatus = async () => {
    try {
      const status = await marketApi.getEarningsStatus();
      setEarningsStatus(status);
    } catch {}
  };

  const loadPaperStatus = async () => {
    setPaperLoading(true);
    try {
      const status = await marketApi.getPaperTradingStatus();
      setPaperStatus(status);
    } catch {}
    setPaperLoading(false);
  };

  const handleCheckEarningsNow = async () => {
    setEarningsChecking(true);
    setEarningsCheckResult(null);
    try {
      const result = await marketApi.checkEarningsNow();
      setEarningsCheckResult(result);
      await loadEarningsStatus();
    } catch (e: any) {
      setEarningsCheckResult({ error: e?.response?.data?.detail || "Failed" });
    }
    setEarningsChecking(false);
  };

  const handleResetEarnings = async () => {
    try {
      await marketApi.resetEarnings();
      setEarningsCheckResult({ reset: true });
      await loadEarningsStatus();
    } catch (e: any) {
      setEarningsCheckResult({ error: e?.response?.data?.detail || "Reset failed" });
    }
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
      {showRiskModal && (
        <RiskProfileModal
          currentUser={currentUser}
          isHebrew={isHe}
          onClose={() => setShowRiskModal(false)}
          onSaved={(updated) => setCurrentUser(updated)}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{isHe ? "לוח בקרה - קרן גידור" : "Fund Dashboard"}</h1>
          <p className="text-gray-400 text-sm mt-1">
            {isHe ? "תצוגה מקצועית של הקרן — Long/Short Equity" : "Professional fund view — Long/Short Equity"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowRiskModal(true)}
            className="text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 px-3 py-1.5 rounded-lg"
          >
            {isHe ? "פרופיל סיכון" : "Risk Profile"}
          </button>
          <Link to="/dashboard" className="text-sm text-gray-400 hover:text-gray-200">
            {isHe ? "← דשבורד רגיל" : "← Standard Dashboard"}
          </Link>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-2 border-b border-gray-800 pb-0">
        {[
          { key: "fund", he: "ניהול קרן", en: "Fund Ops" },
          { key: "performance", he: "ביצועים", en: "Performance" },
          { key: "sectors", he: "סקטורים", en: "Sectors" },
          { key: "earnings", he: "דוחות קרובים", en: "Earnings" },
          { key: "compare", he: "השוואת מניות", en: "Compare" },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key as any)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${
              activeTab === tab.key
                ? "border-blue-500 text-blue-400 bg-blue-900/10"
                : "border-transparent text-gray-400 hover:text-gray-200"
            }`}
          >
            {isHe ? tab.he : tab.en}
          </button>
        ))}
      </div>

      {/* Non-Fund Tabs */}
      {activeTab === "performance" && (
        <div className="space-y-6">
          <PerformanceComparisonChart isHe={isHe} />
          <PerformanceTimelineChart isHe={isHe} />
          <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">
            <PerformanceDashboard isHebrew={isHe} />
          </div>
        </div>
      )}
      {activeTab === "sectors" && (
        <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6">
          <h2 className="font-bold mb-4">{isHe ? "ביצועי סקטורים" : "Sector Performance"}</h2>
          <SectorDashboard isHebrew={isHe} />
        </div>
      )}
      {activeTab === "earnings" && (
        <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6">
          <h2 className="font-bold mb-4">{isHe ? "דוחות רווחים קרובים" : "Upcoming Earnings"}</h2>
          <EarningsCalendar isHebrew={isHe} daysAhead={30} />
        </div>
      )}
      {activeTab === "compare" && (
        <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6">
          <h2 className="font-bold mb-4">{isHe ? "השוואת מניות" : "Stock Comparison"}</h2>
          <StockComparison isHebrew={isHe} />
        </div>
      )}

      {/* Fund Operations Tab Content */}
      {activeTab === "fund" && (<>

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
                <div className="bg-blue-900/20 border border-blue-900/40 rounded-xl p-3">
                  <p className="text-xs text-blue-400">{isHe ? "ממתינות לסריקה היום" : "Today's Scan Pool"}</p>
                  <p className="text-xl font-bold text-blue-400">{universeStats.active_pool}</p>
                  <p className="text-xs text-gray-500">{isHe ? "מניות לניתוח AI" : "stocks for AI analysis"}</p>
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
                : `${isHe ? "נוספו" : "Inserted"} ${universeResult.inserted} | ${isHe ? "עודכנו" : "Updated"} ${universeResult.updated ?? 0} | ${isHe ? "סה\"כ" : "Total"} ${universeResult.total ?? ""}`}
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
              ? "בוחר 100 מניות מתוך ~900 לניתוח AI יומי לפי רוטציה — מניות שלא נותחו לאחרונה מקבלות עדיפות. ה-AI מחליט בעצמו לקנות/למכור/לדלג. כיסוי מלא של כל היקום תוך ~9 ימים."
              : "Selects 100 stocks from ~900 for daily AI analysis by rotation — stocks not recently analyzed get priority. The AI freely decides BUY/SELL/HOLD. Full universe coverage in ~9 days."}
          </p>

          {universeStats && universeStats.top_candidates?.length > 0 ? (
            <div className="space-y-2 mb-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide">
                {isHe ? `מניות לסריקת היום (${universeStats.active_pool} נבחרו)` : `Today's Scan Queue (${universeStats.active_pool} selected)`}
              </p>
              <div className="grid grid-cols-5 gap-1">
                {universeStats.top_candidates.map((c) => (
                  <span key={c.symbol} className="font-mono font-bold text-white text-xs bg-gray-800 rounded px-1.5 py-1 text-center">
                    {c.symbol}
                  </span>
                ))}
              </div>
              {universeStats.active_pool > universeStats.top_candidates.length && (
                <p className="text-xs text-gray-600">
                  {isHe
                    ? `+ ${universeStats.active_pool - universeStats.top_candidates.length} מניות נוספות`
                    : `+ ${universeStats.active_pool - universeStats.top_candidates.length} more stocks`}
                </p>
              )}
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
                  <span className="text-blue-300">{isHe ? "נבחרו לסריקה" : "Selected for scan"}: {screenerResult.activated}</span>
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Earnings Monitoring */}
      <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-bold">{isHe ? "מעקב דוחות כספיים" : "Earnings Monitoring"}</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              {isHe
                ? "בודק כל יום ב-07:30 — כשמגיעים ≥20 דוחות חדשים מתחילה סריקה רבעונית אוטומטית"
                : "Checks daily at 07:30 — when ≥20 fresh earnings arrive, quarterly scan triggers automatically"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCheckEarningsNow}
              disabled={earningsChecking}
              className="text-xs bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white px-3 py-1.5 rounded-lg"
            >
              {earningsChecking ? (isHe ? "בודק..." : "Checking...") : (isHe ? "בדוק עכשיו" : "Check Now")}
            </button>
            <button
              onClick={handleResetEarnings}
              className="text-xs text-red-400 hover:text-red-300 border border-red-900/40 px-2 py-1.5 rounded-lg"
              title={isHe ? "מחק את כל נתוני הדוחות מ-Redis" : "Clear all earnings data from Redis"}
            >
              {isHe ? "איפוס" : "Reset"}
            </button>
            <button
              onClick={loadEarningsStatus}
              className="text-xs text-gray-400 hover:text-gray-200"
            >
              {isHe ? "רענן" : "Refresh"}
            </button>
          </div>
        </div>

        {/* Check result */}
        {earningsCheckResult && (
          <div className={`mb-4 p-3 rounded-xl text-xs ${earningsCheckResult.error ? "bg-red-900/20 text-red-400" : "bg-blue-900/20 text-blue-300"}`}>
            {earningsCheckResult.error ? earningsCheckResult.error : (
              earningsCheckResult.skipped
                ? (isHe ? `דולג: ${earningsCheckResult.reason}` : `Skipped: ${earningsCheckResult.reason}`)
                : (isHe
                    ? `נמצאו ${earningsCheckResult.past_confirmed ?? earningsCheckResult.fresh_this_run ?? 0} דוחות חדשים | סה"כ בתור: ${earningsCheckResult.queued_total}/${earningsCheckResult.trigger_at}`
                    : `Found ${earningsCheckResult.past_confirmed ?? earningsCheckResult.fresh_this_run ?? 0} new | Queue: ${earningsCheckResult.queued_total}/${earningsCheckResult.trigger_at}`)
            )}
          </div>
        )}

        {earningsStatus ? (
          <>
            {/* FMP not configured warning */}
            {!earningsStatus.fmp_configured && (
              <div className="mb-4 p-3 rounded-xl bg-yellow-900/20 border border-yellow-800/40 text-xs text-yellow-300">
                {isHe
                  ? "FMP_API_KEY לא מוגדר — הוסף ב-Railway כדי להפעיל מעקב דוחות"
                  : "FMP_API_KEY not set — add it in Railway to enable earnings tracking"}
              </div>
            )}

            {/* Progress bar */}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-sm font-medium">
                  {isHe ? "דוחות שנאספו" : "Earnings collected"}
                </span>
                <span className="text-sm font-bold">
                  {earningsStatus.queue_count}
                  <span className="text-gray-500 font-normal"> / {earningsStatus.trigger_at}</span>
                </span>
              </div>
              <div className="w-full bg-gray-800 rounded-full h-2.5">
                <div
                  className={`h-2.5 rounded-full transition-all ${
                    earningsStatus.scan_triggered
                      ? "bg-green-500"
                      : earningsStatus.queue_count >= earningsStatus.trigger_at
                      ? "bg-orange-500"
                      : "bg-blue-500"
                  }`}
                  style={{
                    width: `${Math.min(100, (earningsStatus.queue_count / earningsStatus.trigger_at) * 100)}%`,
                  }}
                />
              </div>
            </div>

            {/* Status badge */}
            <div className="mb-4">
              {earningsStatus.scan_triggered ? (
                <div className="inline-flex items-center gap-2 bg-green-900/30 border border-green-800/50 rounded-lg px-3 py-1.5 text-xs text-green-300">
                  <span className="w-2 h-2 bg-green-400 rounded-full" />
                  {isHe
                    ? `סריקה רבעונית הושקה — ${earningsStatus.scan_triggered}`
                    : `Quarterly scan triggered — ${earningsStatus.scan_triggered}`}
                </div>
              ) : earningsStatus.queue_count >= earningsStatus.trigger_at ? (
                <div className="inline-flex items-center gap-2 bg-orange-900/30 border border-orange-800/50 rounded-lg px-3 py-1.5 text-xs text-orange-300">
                  <span className="w-2 h-2 bg-orange-400 rounded-full animate-pulse" />
                  {isHe ? "מוכן — מעל לסף, ממתין להשקה" : "Ready — above threshold, pending trigger"}
                </div>
              ) : (
                <div className="inline-flex items-center gap-2 bg-gray-800 rounded-lg px-3 py-1.5 text-xs text-gray-400">
                  <span className="w-2 h-2 bg-gray-500 rounded-full" />
                  {isHe
                    ? `אוסף דוחות... (${earningsStatus.trigger_at - earningsStatus.queue_count} נדרשים עוד)`
                    : `Collecting... (${earningsStatus.trigger_at - earningsStatus.queue_count} more needed)`}
                </div>
              )}
            </div>

            {/* Confirmed — already reported */}
            {earningsStatus.companies?.length > 0 && (
              <div className="mb-3">
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                  {isHe ? "פרסמו דוחות (נספרים לסף)" : "Already reported (counted toward threshold)"}
                </p>
                <div className="grid grid-cols-2 gap-1.5 max-h-36 overflow-y-auto pr-1">
                  {earningsStatus.companies.map((c: any) => (
                    <div key={c.symbol} className="flex items-center justify-between bg-green-900/20 border border-green-900/30 rounded-lg px-2.5 py-1.5">
                      <span className="font-mono font-bold text-xs text-white">{c.symbol}</span>
                      <span className="text-xs text-green-400">{c.earnings_date}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Pending — upcoming (not yet reported) */}
            {earningsStatus.pending?.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                  {isHe ? "עתידיים — ממתינים לפרסום" : "Upcoming — not yet reported"}
                </p>
                <div className="grid grid-cols-2 gap-1.5 max-h-36 overflow-y-auto pr-1">
                  {earningsStatus.pending.map((c: any) => (
                    <div key={c.symbol} className="flex items-center justify-between bg-gray-800/40 border border-gray-700/40 rounded-lg px-2.5 py-1.5">
                      <span className="font-mono font-bold text-xs text-gray-300">{c.symbol}</span>
                      <span className="text-xs text-gray-500">{c.earnings_date}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Last check */}
            {earningsStatus.last_check && (
              <p className="text-xs text-gray-600 mt-3">
                {isHe ? "בדיקה אחרונה:" : "Last check:"}{" "}
                {new Date(earningsStatus.last_check).toLocaleString(isHe ? "he-IL" : "en-US")}
              </p>
            )}
          </>
        ) : (
          <div className="text-center py-6 text-gray-500 text-sm">
            {isHe ? "טוען נתוני דוחות..." : "Loading earnings data..."}
          </div>
        )}
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

      {/* Alpaca Paper Trading Panel */}
      <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-bold">{isHe ? "מסחר נייר (Alpaca)" : "Paper Trading (Alpaca)"}</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              {isHe
                ? "AI מבצע עסקאות נייר אוטומטיות לפי ההמלצות — לבדיקת ביצועי האסטרטגיה"
                : "AI executes paper trades automatically based on recommendations — strategy performance tracking"}
            </p>
          </div>
          <button
            onClick={loadPaperStatus}
            disabled={paperLoading}
            className="text-xs text-gray-400 hover:text-gray-200 disabled:text-gray-600"
          >
            {paperLoading ? (isHe ? "טוען..." : "Loading...") : (isHe ? "רענן" : "Refresh")}
          </button>
        </div>

        {paperStatus === null ? (
          <div className="text-center py-6 text-gray-500 text-sm">
            {paperLoading ? (isHe ? "טוען..." : "Loading...") : (isHe ? "לא ניתן לטעון נתוני Alpaca" : "Could not load Alpaca data")}
          </div>
        ) : !paperStatus.configured ? (
          <div className="p-4 bg-yellow-900/20 border border-yellow-800/40 rounded-xl text-sm text-yellow-300 space-y-2">
            <p className="font-medium">{isHe ? "Alpaca לא מוגדר" : "Alpaca not configured"}</p>
            <p className="text-xs text-yellow-400/70">
              {isHe
                ? "כדי להפעיל מסחר נייר, הוסף את המשתנים הבאים ב-Railway:"
                : "To enable paper trading, add these variables in Railway:"}
            </p>
            <ul className="text-xs font-mono space-y-0.5 text-yellow-400/90">
              <li>ALPACA_API_KEY=<span className="text-gray-400">your_key</span></li>
              <li>ALPACA_API_SECRET=<span className="text-gray-400">your_secret</span></li>
            </ul>
            <p className="text-xs text-gray-500">
              {isHe ? "הרשם בחינם בכתובת" : "Register free at"}{" "}
              <span className="text-blue-400 font-mono">alpaca.markets</span>{" "}
              {isHe ? "→ Paper Trading" : "→ Paper Trading"}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Account Summary */}
            {paperStatus.account && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-gray-800 rounded-xl p-3">
                  <p className="text-xs text-gray-400 mb-1">{isHe ? "שווי תיק" : "Portfolio Value"}</p>
                  <p className="text-lg font-bold text-white">
                    ${Number(paperStatus.account.portfolio_value || 0).toLocaleString("en", { maximumFractionDigits: 0 })}
                  </p>
                </div>
                <div className="bg-gray-800 rounded-xl p-3">
                  <p className="text-xs text-gray-400 mb-1">{isHe ? "מזומן" : "Cash"}</p>
                  <p className="text-lg font-bold text-blue-400">
                    ${Number(paperStatus.account.cash || 0).toLocaleString("en", { maximumFractionDigits: 0 })}
                  </p>
                </div>
                <div className="bg-gray-800 rounded-xl p-3">
                  <p className="text-xs text-gray-400 mb-1">{isHe ? "הון עצמי" : "Equity"}</p>
                  <p className="text-lg font-bold text-white">
                    ${Number(paperStatus.account.equity || 0).toLocaleString("en", { maximumFractionDigits: 0 })}
                  </p>
                </div>
                <div className="bg-gray-800 rounded-xl p-3">
                  <p className="text-xs text-gray-400 mb-1">{isHe ? "כוח קנייה" : "Buying Power"}</p>
                  <p className="text-lg font-bold text-green-400">
                    ${Number(paperStatus.account.buying_power || 0).toLocaleString("en", { maximumFractionDigits: 0 })}
                  </p>
                </div>
              </div>
            )}

            {/* Open Positions */}
            {paperStatus.positions && paperStatus.positions.length > 0 ? (
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                  {isHe ? "פוזיציות פתוחות" : "Open Positions"} ({paperStatus.positions.length})
                </p>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-gray-500 border-b border-gray-800">
                        <th className="text-left py-1.5">{isHe ? "מניה" : "Symbol"}</th>
                        <th className="text-right py-1.5">{isHe ? "כמות" : "Qty"}</th>
                        <th className="text-right py-1.5">{isHe ? "מחיר ממוצע" : "Avg Price"}</th>
                        <th className="text-right py-1.5">{isHe ? "שווי שוק" : "Market Value"}</th>
                        <th className="text-right py-1.5">{isHe ? "רווח/הפסד" : "Unrealized P&L"}</th>
                        <th className="text-right py-1.5">%</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-800/50">
                      {paperStatus.positions.map((pos: any) => {
                        const pnl = Number(pos.unrealized_pl || 0);
                        const pnlPct = Number(pos.unrealized_plpc || 0) * 100;
                        return (
                          <tr key={pos.symbol} className="hover:bg-gray-800/30">
                            <td className="py-1.5 font-mono font-bold text-white">{pos.symbol}</td>
                            <td className="py-1.5 text-right text-gray-300">{Number(pos.qty).toFixed(2)}</td>
                            <td className="py-1.5 text-right text-gray-300">${Number(pos.avg_entry_price).toFixed(2)}</td>
                            <td className="py-1.5 text-right text-gray-300">${Number(pos.market_value).toLocaleString("en", { maximumFractionDigits: 0 })}</td>
                            <td className={`py-1.5 text-right font-medium ${pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                              {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}
                            </td>
                            <td className={`py-1.5 text-right ${pnlPct >= 0 ? "text-green-400" : "text-red-400"}`}>
                              {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(1)}%
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <p className="text-xs text-gray-500 text-center py-3">
                {isHe ? "אין פוזיציות פתוחות" : "No open positions yet — AI will trade as recommendations are approved"}
              </p>
            )}

            {/* Recent Orders */}
            {paperStatus.recent_orders && paperStatus.recent_orders.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                  {isHe ? "עסקאות אחרונות" : "Recent Orders"}
                </p>
                <div className="space-y-1">
                  {paperStatus.recent_orders.slice(0, 5).map((order: any, i: number) => (
                    <div key={i} className="flex items-center justify-between bg-gray-800/40 rounded-lg px-3 py-1.5 text-xs">
                      <div className="flex items-center gap-2">
                        <span className={`font-mono font-bold w-6 text-center ${order.side === "buy" ? "text-green-400" : "text-red-400"}`}>
                          {order.side === "buy" ? "B" : "S"}
                        </span>
                        <span className="font-mono font-bold text-white">{order.symbol}</span>
                        <span className="text-gray-400">{Number(order.qty || order.notional || 0).toFixed(2)}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`px-1.5 py-0.5 rounded text-xs ${order.status === "filled" ? "bg-green-900/40 text-green-400" : "bg-gray-700 text-gray-400"}`}>
                          {order.status}
                        </span>
                        <span className="text-gray-500">{order.filled_avg_price ? `$${Number(order.filled_avg_price).toFixed(2)}` : ""}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Simulation Panel */}
      <div className="bg-gray-900 rounded-2xl p-6 border border-purple-900/40">
        <h2 className="font-bold mb-1 text-purple-300">
          {isHe ? "🧪 לוח סימולציה — בדיקת זרימה מלאה" : "🧪 Simulation Panel — Full Flow Test"}
        </h2>
        <p className="text-xs text-gray-400 mb-5">
          {isHe
            ? "בדוק את כל המערכת מקצה לקצה: סריקת מניה → רשימת מאסטר → פוזיציה → TA Alert → התראה"
            : "Test the full system: stock scan → master list → position → TA alert → notification"}
        </p>

        {/* Symbol input */}
        <div className="mb-5 flex items-center gap-3">
          <label className="text-xs text-gray-400 w-24">{isHe ? "מניה לבדיקה:" : "Test symbol:"}</label>
          <input
            value={simSymbol}
            onChange={e => setSimSymbol(e.target.value.toUpperCase())}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm font-mono w-28 text-white"
            placeholder="e.g. MU"
          />
        </div>

        <div className="space-y-3">
          {[
            {
              step: 1,
              icon: "⚡",
              title: isHe ? "הרץ סריקת AI מלאה" : "Run Full AI Scan",
              desc: isHe ? `Claude מנתח את ${simSymbol} ומחליט BUY/SELL/HOLD` : `Claude analyzes ${simSymbol} and decides BUY/SELL/HOLD`,
              action: async () => {
                const r = await marketApi.scanPoolNow();
                return r;
              },
            },
            {
              step: 2,
              icon: "📋",
              title: isHe ? "פרסם רשימת מאסטר" : "Publish Master List",
              desc: isHe ? "מפרסם את ה-50 המניות הטובות ביותר לכל המשתמשים" : "Publishes top 50 stocks to all users",
              action: async () => marketApi.publishMasterList(),
            },
            {
              step: 3,
              icon: "💼",
              title: isHe ? `צור פוזיציית בדיקה (${simSymbol})` : `Create Test Position (${simSymbol})`,
              desc: isHe ? `מוסיף ${simSymbol} לתיק שלך (10 יחידות) כדי שה-TA scan ישלח לך התראות` : `Adds ${simSymbol} to your portfolio (10 units) so TA scan alerts fire to you`,
              action: async () => marketApi.simulateCreatePosition(simSymbol),
              removeAction: async () => marketApi.simulateRemovePosition(simSymbol),
            },
            {
              step: 4,
              icon: "📊",
              title: isHe ? "הפעל TA Scan עכשיו" : "Run TA Scan Now",
              desc: isHe ? "ניתוח טכני מיידי — אם יש סיגנל BUY/SELL תקבל התראה" : "Immediate technical analysis — if BUY/SELL signal, you get an alert",
              action: async () => marketApi.simulateTaScan(),
            },
            {
              step: 5,
              icon: "🔔",
              title: isHe ? "שלח התראת בדיקה" : "Send Test Notification",
              desc: isHe ? "שולח התראה ישירה לכל הערוצים (Push + SMS + Email + תיבת דואר)" : "Sends alert to all channels (Push + SMS + Email + Inbox)",
              action: async () => marketApi.simulateTestNotification(),
            },
          ].map(({ step, icon, title, desc, action, removeAction }: any) => (
            <div key={step} className="flex items-start gap-4 bg-gray-800/40 rounded-xl p-4 border border-gray-700/40">
              <div className="flex flex-col items-center gap-1 shrink-0">
                <span className="w-7 h-7 rounded-full bg-purple-900/60 border border-purple-700/50 flex items-center justify-center text-xs font-bold text-purple-300">
                  {step}
                </span>
                <span className="text-lg">{icon}</span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white">{title}</p>
                <p className="text-xs text-gray-500 mt-0.5">{desc}</p>
                {simStep[step] && (
                  step === 5 && simStep[step].diagnostics ? (
                    <div className="mt-2 space-y-1.5">
                      {/* Channel status */}
                      {["push", "sms", "email", "telegram"].map((ch) => {
                        const d = simStep[step].diagnostics[ch];
                        const sent = simStep[step].channels?.includes(ch) || (ch === "telegram" && d?.test_sent);
                        const icon = sent ? "✅" : d?.will_send === false || d?.configured === false ? "❌" : "⚠️";
                        const issues = [];
                        if (ch === "telegram") {
                          if (!d?.has_bot_token) issues.push(isHe ? "אין BOT_TOKEN" : "no BOT_TOKEN");
                          else if (!d?.has_chat_id) issues.push(isHe ? "אין CHAT_ID" : "no CHAT_ID");
                        } else if (!d?.enabled) issues.push(isHe ? "כבוי בהגדרות" : "disabled in settings");
                        else if (ch === "push" && !d?.has_token) issues.push(isHe ? "אין push token" : "no push token");
                        else if (ch === "sms" && !d?.has_phone) issues.push(isHe ? "אין טלפון" : "no phone");
                        else if (ch === "sms" && !d?.twilio_configured) issues.push(isHe ? "Twilio לא מוגדר" : "Twilio not configured");
                        else if (ch === "email" && !d?.sendgrid_configured) issues.push(isHe ? "SendGrid לא מוגדר" : "SendGrid not configured");
                        return (
                          <div key={ch} className={`flex items-center gap-2 text-xs px-2 py-1 rounded ${sent ? "bg-green-900/20 text-green-300" : "bg-gray-800/60 text-gray-400"}`}>
                            <span>{icon}</span>
                            <span className="uppercase font-mono w-10">{ch}</span>
                            <span>{sent ? (isHe ? "נשלח!" : "Sent!") : issues.join(", ") || (isHe ? "נכשל" : "failed")}</span>
                          </div>
                        );
                      })}
                      {simStep[step].channels?.length === 0 && (
                        <p className="text-xs text-yellow-500 mt-1">
                          {isHe ? "אף ערוץ לא נשלח — ראה הסבר למטה" : "No channels sent — see explanation below"}
                        </p>
                      )}
                    </div>
                  ) : (
                    <div className={`mt-2 p-2 rounded-lg text-xs ${simStep[step].error ? "bg-red-900/20 text-red-400" : "bg-green-900/20 text-green-300"}`}>
                      {simStep[step].error
                        ? simStep[step].error
                        : JSON.stringify(simStep[step]).slice(0, 120)}
                    </div>
                  )
                )}
              </div>
              <div className="flex flex-col gap-1 shrink-0">
                <button
                  disabled={simLoading[step]}
                  onClick={async () => {
                    setSimLoading(l => ({ ...l, [step]: true }));
                    setSimStep(s => ({ ...s, [step]: null }));
                    try {
                      const r = await action();
                      setSimStep(s => ({ ...s, [step]: r }));
                    } catch (e: any) {
                      setSimStep(s => ({ ...s, [step]: { error: e?.response?.data?.detail || String(e) } }));
                    }
                    setSimLoading(l => ({ ...l, [step]: false }));
                  }}
                  className="text-xs bg-purple-700 hover:bg-purple-600 disabled:bg-gray-700 text-white px-3 py-1.5 rounded-lg"
                >
                  {simLoading[step] ? "..." : (isHe ? "הרץ" : "Run")}
                </button>
                {removeAction && (
                  <button
                    disabled={simLoading[`${step}_rm`]}
                    onClick={async () => {
                      setSimLoading(l => ({ ...l, [`${step}_rm`]: true }));
                      try {
                        const r = await removeAction();
                        setSimStep(s => ({ ...s, [step]: r }));
                      } catch (e: any) {
                        setSimStep(s => ({ ...s, [step]: { error: e?.response?.data?.detail || String(e) } }));
                      }
                      setSimLoading(l => ({ ...l, [`${step}_rm`]: false }));
                    }}
                    className="text-xs bg-red-900/60 hover:bg-red-800/60 disabled:bg-gray-700 text-red-300 px-3 py-1.5 rounded-lg"
                  >
                    {simLoading[`${step}_rm`] ? "..." : (isHe ? "מחק" : "Remove")}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 text-xs text-gray-500 space-y-1 border-t border-gray-800 pt-4">
          <p className="font-medium text-gray-400">{isHe ? "מה נדרש לכל ערוץ?" : "What each channel needs:"}</p>
          <p>📧 <strong>Email</strong> — {isHe ? "הגדר SENDGRID_API_KEY אמיתי ב-Railway (לא SG.xxxxx). חינם עד 100 מיילים/יום. אימות שולח ב-sendgrid.com" : "Set real SENDGRID_API_KEY in Railway (not SG.xxxxx). Free up to 100 emails/day. Verify sender at sendgrid.com"}</p>
          <p>📱 <strong>SMS</strong> — {isHe ? "הגדר TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER אמיתיים ב-Railway. טלפון משתמש חייב להיות בפורמט +972XXXXXXXXX" : "Set real TWILIO_ACCOUNT_SID, AUTH_TOKEN, FROM_NUMBER in Railway. User phone must be +972XXXXXXXXX format"}</p>
          <p>✈️ <strong>Telegram</strong> — {isHe ? "צור Bot ב-@BotFather → הגדר TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID ב-Railway. שלח /start לבוט כדי לקבל את ה-Chat ID" : "Create Bot via @BotFather → set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in Railway. Send /start to bot to get Chat ID"}</p>
          <p>🔔 <strong>Push</strong> — {isHe ? "דורש Firebase FCM + הרשאת דפדפן. הדפדפן חייב לאשר התראות ולשמור push_token" : "Requires Firebase FCM + browser permission. Browser must grant notifications and register push_token"}</p>
          <p className="mt-2 text-gray-600">{isHe ? "אחרי הסימולציה — לחץ 'מחק' בשלב 3 להסרת הפוזיציה" : "After simulation — click 'Remove' in Step 3 to delete the test position"}</p>
        </div>
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
      </>)}
    </div>
  );
};

export default FundDashboard;
