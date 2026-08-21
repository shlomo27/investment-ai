import React, { useEffect, useState, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../store";
import { fetchPortfolioSummary, fetchPortfolioRisk } from "../store/slices/portfolioSlice";
import { fetchRecommendations } from "../store/slices/notificationsSlice";
import { marketApi } from "../api/client";
import { UniverseStats, UniversePool, ScreenerStatus, RecommendationType } from "../types";
import PerformanceDashboard from "../components/Performance/PerformanceDashboard";
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
  const [screenerStatus, setScreenerStatus] = useState<ScreenerStatus | null>(null);
  const screenerWasRunning = useRef(false);
  const [pool, setPool] = useState<UniversePool | null>(null);
  const [poolOpen, setPoolOpen] = useState(false);
  const [poolLoading, setPoolLoading] = useState(false);
  const [universeLoading, setUniverseLoading] = useState(false);
  const [universeResult, setUniverseResult] = useState<any>(null);
  const [scanRunning, setScanRunning] = useState(false);
  const [scanResult, setScanResult] = useState<any>(null);
  const [scanStatus, setScanStatus] = useState<any>(null);
  const [earningsStatus, setEarningsStatus] = useState<any>(null);
  const [earningsChecking, setEarningsChecking] = useState(false);
  const [earningsCheckResult, setEarningsCheckResult] = useState<any>(null);
  const [batchResult, setBatchResult] = useState<any>(null);
  const [batchStarting, setBatchStarting] = useState(false);

  const handleRequeueReporters = async () => {
    setBatchStarting(true);
    setBatchResult(null);
    try {
      const res = await marketApi.requeueReporters();
      setBatchResult({
        started: false,
        reason: res.requeued
          ? `${res.requeued} חברות שדיווחו הוחזרו לתור לניתוח מחדש (מתוך ${res.needed} שנמצאו). התור: ${res.queue_len}.`
          : (res.reason || "לא נמצאו חברות שדורשות ניתוח מחדש"),
      });
      await loadEarningsStatus();
    } catch (e: any) {
      setBatchResult({ error: e?.response?.data?.detail || "Failed" });
    }
    setBatchStarting(false);
  };

  const handleRunQuarterlyBatch = async () => {
    setBatchStarting(true);
    setBatchResult(null);
    try {
      const res = await marketApi.runQuarterlyBatch();
      setBatchResult(res);
    } catch (e: any) {
      setBatchResult({ error: e?.response?.data?.detail || "Failed" });
    }
    setBatchStarting(false);
  };

  // Dashboard tab state
  const [activeTab, setActiveTab] = useState<"fund" | "performance" | "sectors" | "earnings" | "compare">("fund");

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
    loadScreenerStatus();
  }, [dispatch]);

  // The screener runs for minutes in the background. Poll while it is running
  // so the panel shows live progress instead of an unexplained failure.
  useEffect(() => {
    if (!screenerStatus?.running) return;
    const id = setInterval(loadScreenerStatus, 5000);
    return () => clearInterval(id);
  }, [screenerStatus?.running]);

  const loadUniverseStats = async () => {
    try {
      const stats = await marketApi.getUniverseStats();
      setUniverseStats(stats);
    } catch {}
  };

  // Fetched on demand — the full pool is ~140 rows with a per-symbol analysis
  // lookup, not worth loading for everyone who opens the dashboard.
  const openPool = async () => {
    setPoolOpen(true);
    if (pool) return;
    setPoolLoading(true);
    try {
      setPool(await marketApi.getUniversePool());
    } catch {}
    setPoolLoading(false);
  };

  const loadScreenerStatus = async () => {
    try {
      const status = await marketApi.getScreenerStatus();
      setScreenerStatus(status);
      setScreenerRunning(status.running);
      if (!status.running) {
        if (status.error) setScreenerResult({ error: status.error });
        else if (status.result) setScreenerResult(status.result);
        // Only refresh the pool numbers on the run→done transition, so the
        // idle poll doesn't refetch stats on every mount.
        if (screenerWasRunning.current) await loadUniverseStats();
      }
      screenerWasRunning.current = status.running;
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
    setScreenerResult(null);
    try {
      // Returns immediately — the run itself happens in the background and is
      // followed via loadScreenerStatus polling.
      const res = await marketApi.runScreener();
      if (res?.started || res?.already_running) {
        setScreenerRunning(true);
        screenerWasRunning.current = true;
        setScreenerStatus({ running: true, phase: res.phase || "מתחיל" });
      } else {
        setScreenerResult({ error: res?.message || "ההרצה לא התחילה" });
      }
    } catch (e: any) {
      setScreenerResult({
        error:
          e?.response?.data?.detail ||
          (e?.code === "ECONNABORTED"
            ? "הבקשה עברה את זמן ההמתנה"
            : e?.message || "ההרצה נכשלה"),
      });
    }
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

  // Still used by the holdings table further down this screen.
  const positions = summary?.positions || [];

  // Compute approved recommendation breakdown
  // ACTIONED = the user marked it as bought at their broker — the
  // recommendation is still live and must count in the signal summary.
  const approvedRecs = recommendations.filter(
    (r) => r.status === "APPROVED" || r.status === "PRESENTED_TO_USER" || r.status === "ACTIONED"
  );
  const longRecs = approvedRecs.filter(
    (r) => r.recommendation_type === RecommendationType.BUY || r.recommendation_type === RecommendationType.STRONG_BUY
  );
  const shortRecs = approvedRecs.filter(
    (r) => r.recommendation_type === RecommendationType.SELL || r.recommendation_type === RecommendationType.STRONG_SELL
  );

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{isHe ? "לוח ניהול מערכת" : "System Control Panel"}</h1>
          <p className="text-gray-400 text-sm mt-1">
            {isHe ? "מצב הסריקות, המנועים וההמלצות" : "Scans, engines and signal status"}
          </p>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-2 border-b border-gray-800 pb-0">
        {[
          { key: "fund", he: "ניהול תיק", en: "Portfolio Ops" },
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

      {/* Operational status — what an operator actually needs at a glance */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
          <p className="text-xs text-gray-400 mb-1">{isHe ? "המלצות פעילות" : "Active Signals"}</p>
          <p className="text-2xl font-bold text-blue-400">{approvedRecs.length}</p>
          <p className="text-xs text-gray-500">{isHe ? "בפיד הסיגנלים" : "in the signals feed"}</p>
        </div>
        <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
          <p className="text-xs text-gray-400 mb-1">{isHe ? "מניות ביקום" : "Universe"}</p>
          <p className="text-2xl font-bold">{universeStats?.universe_total ?? "—"}</p>
          <p className="text-xs text-gray-500">
            {universeStats?.active_pool ?? "—"} {isHe ? "במאגר הסריקה" : "in scan pool"}
          </p>
        </div>
        <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
          <p className="text-xs text-gray-400 mb-1">{isHe ? "בתור לסריקה" : "Scan Queue"}</p>
          <p className="text-2xl font-bold text-purple-300">{scanStatus?.remaining ?? "—"}</p>
          <p className="text-xs text-gray-500">
            {isHe ? "נותרו בסריקה הרבעונית" : "remaining this sweep"}
          </p>
        </div>
        <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
          <p className="text-xs text-gray-400 mb-1">{isHe ? "דוחות שנאספו" : "Earnings Collected"}</p>
          <p className="text-2xl font-bold text-amber-300">{earningsStatus?.queue_count ?? "—"}</p>
          <p className="text-xs text-gray-500">
            {earningsStatus?.analyzed_count != null && earningsStatus?.companies?.length
              ? `${earningsStatus.analyzed_count}/${earningsStatus.companies.length} ${isHe ? "נותחו" : "analyzed"}`
              : (isHe ? "מחברות שדיווחו" : "from reporters")}
          </p>
        </div>
      </div>

      {/* AI Signal Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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

          {screenerStatus?.running && (
            <div className="mb-4 p-3 rounded-xl bg-blue-900/20 border border-blue-900/40">
              <div className="flex items-center gap-2">
                <span className="inline-block w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                <p className="text-xs text-blue-300">
                  {screenerStatus.phase || (isHe ? "רץ..." : "Running...")}
                </p>
              </div>
              {screenerStatus.downloaded != null && screenerStatus.universe_size ? (
                <div className="mt-2 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 transition-all"
                    style={{
                      width: `${Math.round(
                        (screenerStatus.downloaded / screenerStatus.universe_size) * 100
                      )}%`,
                    }}
                  />
                </div>
              ) : null}
              <p className="text-xs text-gray-500 mt-2">
                {isHe
                  ? "ההרצה לוקחת כמה דקות ורצה בשרת — אפשר לעזוב את הדף ולחזור."
                  : "The run takes a few minutes on the server — you can leave the page and come back."}
              </p>
            </div>
          )}
          <p className="text-xs text-gray-400 mb-4">
            {isHe
              ? "מדרג כל בוקר את כל ~900 מניות היקום לפי מומנטום (50% מומנטום 3 חודשים, 30% מומנטום 6 חודשים, 20% נפח) ובוחר את המאגר הפעיל: 80 החזקות ביותר ללונג + 20 החלשות ביותר לשורט. מניה שנכנסה למאגר נשארת בו לפחות שבוע — כך היא מובטחת להיכלל בסריקה השבועית המעמיקה ולא נופלת בין הכיסאות."
              : "Ranks all ~900 universe stocks every morning by momentum (50% 3-month, 30% 6-month, 20% volume) and selects the active pool: top 80 for LONG + weakest 20 for SHORT. A stock that enters the pool is held for at least a week, so it is guaranteed to be covered by the weekly deep scan."}
          </p>

          {universeStats?.pool_changes?.ran_at && (
            <div className="mb-4 bg-gray-800/50 rounded-xl p-3 space-y-2">
              <p className="text-xs text-gray-500 uppercase tracking-wide">
                {isHe ? "שינויים בהרצה האחרונה" : "Last run changes"}
                {" · "}
                {new Date(universeStats.pool_changes.ran_at).toLocaleString(isHe ? "he-IL" : "en-US")}
              </p>

              {(() => {
                const fetched = universeStats.pool_changes.data_fetched;
                const size = universeStats.pool_changes.universe_size;
                if (fetched == null || !size) return null;
                const pct = Math.round((fetched / size) * 100);
                const tone =
                  pct >= 90 ? "text-green-400" : pct >= 70 ? "text-yellow-400" : "text-red-400";
                return (
                  <div className="border-b border-gray-700/60 pb-2">
                    <p className="text-xs text-gray-400">
                      {isHe ? "נתוני מחיר נמשכו עבור" : "Price data fetched for"}{" "}
                      <span className={`font-bold ${tone}`}>
                        {fetched}/{size} ({pct}%)
                      </span>
                    </p>
                    {universeStats.pool_changes.aborted ? (
                      <p className="text-xs text-yellow-400 mt-0.5">
                        {universeStats.pool_changes.abort_reason ||
                          (isHe
                            ? "לא היו מספיק נתונים לדירוג — המאגר נשאר ללא שינוי."
                            : "Not enough data to rank — the pool was left unchanged.")}
                      </p>
                    ) : pct < 90 ? (
                      <div className="mt-0.5 space-y-1">
                        <p className="text-xs text-gray-500">
                          {isHe
                            ? "ספק הנתונים הגביל חלק מהבקשות — הדירוג נקבע על בסיס חלקי. מניה בלי נתוני מחיר לא נכנסת למאגר."
                            : "The data provider throttled some requests — the ranking was decided on partial data. A stock without price data is not activated into the pool."}
                        </p>
                        {(universeStats.pool_changes.no_data_sample?.length ?? 0) > 0 && (
                          <details className="text-xs">
                            <summary className="cursor-pointer text-gray-500 hover:text-gray-400">
                              {isHe
                                ? `אילו מניות חסרות? (${universeStats.pool_changes.no_data_count})`
                                : `Which stocks are missing? (${universeStats.pool_changes.no_data_count})`}
                            </summary>
                            <div className="mt-1 flex flex-wrap gap-1">
                              {universeStats.pool_changes.no_data_sample!.map((s) => (
                                <span key={s} className="font-mono bg-gray-800 text-gray-400 rounded px-1.5 py-0.5">
                                  {s}
                                </span>
                              ))}
                            </div>
                          </details>
                        )}
                      </div>
                    ) : null}
                  </div>
                );
              })()}

              <div>
                <p className="text-xs text-green-400 mb-1">
                  {isHe ? "נכנסו" : "Entered"} ({universeStats.pool_changes.entered.length})
                </p>
                {universeStats.pool_changes.entered.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {universeStats.pool_changes.entered.map((s) => (
                      <span key={s} className="font-mono text-xs bg-green-900/25 text-green-300 rounded px-1.5 py-0.5">
                        {s}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-600">{isHe ? "אין" : "None"}</p>
                )}
              </div>

              <div>
                <p className="text-xs text-red-400 mb-1">
                  {isHe ? "יצאו" : "Exited"} ({universeStats.pool_changes.exited.length})
                </p>
                {universeStats.pool_changes.exited.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {universeStats.pool_changes.exited.map((s) => (
                      <span key={s} className="font-mono text-xs bg-red-900/25 text-red-300 rounded px-1.5 py-0.5">
                        {s}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-600">{isHe ? "אין" : "None"}</p>
                )}
              </div>

              {universeStats.pool_changes.held_sticky > 0 && (
                <p className="text-xs text-gray-500">
                  {isHe
                    ? `${universeStats.pool_changes.held_sticky} מניות ירדו מהדירוג אך מוחזקות במאגר עד שיושלם עליהן ניתוח מעמיק`
                    : `${universeStats.pool_changes.held_sticky} stocks dropped out of the ranking but are held until their deep analysis completes`}
                </p>
              )}

              <p className="text-xs text-gray-500 border-t border-gray-700/60 pt-2">
                {isHe
                  ? "⚠️ הרשימה הזאת היא תקציב סריקה בלבד — היא קובעת על אילו מניות מושקע ניתוח AI מעמיק השבוע. יציאה מהרשימה אינה המלצת מכירה. מניה שמשתמש מחזיק או שיש עליה המלצה פעילה ממשיכה להיות מנותחת גם מחוץ למאגר, והמלצת מכירה מגיעה רק מניתוח בפועל."
                  : "⚠️ This list is a scanning budget only — it decides which stocks get deep AI analysis this week. Leaving it is NOT a sell signal. A stock a user holds, or one with a live recommendation, keeps being analyzed even outside the pool; a sell only ever comes from an actual analysis."}
              </p>
            </div>
          )}

          {universeStats && universeStats.top_candidates?.length > 0 ? (
            <div className="space-y-2 mb-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide">
                {isHe ? `מניות לסריקת היום (${universeStats.active_pool} נבחרו)` : `Today's Scan Queue (${universeStats.active_pool} selected)`}
              </p>
              {!poolOpen ? (
                <>
                  <div className="grid grid-cols-5 gap-1">
                    {universeStats.top_candidates.map((c) => (
                      <span key={c.symbol} className="font-mono font-bold text-white text-xs bg-gray-800 rounded px-1.5 py-1 text-center">
                        {c.symbol}
                      </span>
                    ))}
                  </div>
                  {universeStats.active_pool > universeStats.top_candidates.length && (
                    <button
                      onClick={openPool}
                      className="text-xs text-blue-400 hover:text-blue-300 underline"
                    >
                      {isHe
                        ? `+ ${universeStats.active_pool - universeStats.top_candidates.length} מניות נוספות — הצג את כולן`
                        : `+ ${universeStats.active_pool - universeStats.top_candidates.length} more — show all`}
                    </button>
                  )}
                </>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-gray-500">
                      {poolLoading
                        ? (isHe ? "טוען..." : "Loading...")
                        : isHe
                        ? `${pool?.analyzed ?? 0} מתוך ${pool?.count ?? 0} כבר נותחו`
                        : `${pool?.analyzed ?? 0} of ${pool?.count ?? 0} already analyzed`}
                    </p>
                    <button
                      onClick={() => setPoolOpen(false)}
                      className="text-xs text-gray-400 hover:text-gray-300"
                    >
                      {isHe ? "סגור" : "Collapse"}
                    </button>
                  </div>

                  <div className="max-h-96 overflow-y-auto space-y-1 pe-1">
                    {(pool?.stocks || []).map((s) => {
                      const a = s.analysis;
                      const buySide = a && ["BUY", "STRONG_BUY"].includes(a.recommendation_type);
                      const sellSide = a && ["SELL", "STRONG_SELL"].includes(a.recommendation_type);
                      const verdict = !a
                        ? (isHe ? "טרם נותחה" : "not analyzed yet")
                        : a.status === "REJECTED"
                        ? (isHe ? "נדחתה בוועדה" : "rejected")
                        : a.recommendation_type;
                      return (
                        <div
                          key={s.symbol}
                          className="flex items-center gap-2 text-xs bg-gray-800/50 rounded px-2 py-1.5"
                        >
                          <span className="font-mono font-bold text-white w-16 shrink-0">{s.symbol}</span>
                          <span className="text-gray-500 truncate flex-1 min-w-0">{s.name}</span>
                          {s.direction_bias === "SHORT" && (
                            <span className="text-orange-400 shrink-0">📉</span>
                          )}
                          <span
                            className={`shrink-0 ${
                              buySide ? "text-green-400" : sellSide ? "text-red-400" : "text-gray-500"
                            }`}
                          >
                            {verdict}
                          </span>
                          {a ? (
                            <div className="flex gap-1 shrink-0">
                              <Link
                                to={`/research/${a.recommendation_id}`}
                                className="px-1.5 py-0.5 rounded bg-blue-900/40 text-blue-300 hover:bg-blue-900/70"
                              >
                                {isHe ? "כלכלי" : "Fundamental"}
                              </Link>
                              <Link
                                to={`/technical/${a.recommendation_id}`}
                                className="px-1.5 py-0.5 rounded bg-purple-900/40 text-purple-300 hover:bg-purple-900/70"
                              >
                                {isHe ? "טכני" : "Technical"}
                              </Link>
                            </div>
                          ) : (
                            <span className="text-gray-600 shrink-0">
                              {isHe ? "בתור לסריקה" : "queued"}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
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
                  {isHe ? "דורגו" : "Scored"} {screenerResult.passed_filter ?? 0} |{" "}
                  <span className="text-blue-300">
                    {isHe ? "במאגר" : "In pool"}: {screenerResult.pool_size ?? screenerResult.selected ?? 0}
                  </span>{" "}
                  | <span className="text-green-400">+{screenerResult.entered ?? 0}</span>{" "}
                  <span className="text-red-400">−{screenerResult.exited ?? 0}</span>
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
                ? "בודק כל יום ב-07:30. כל חברה שמפרסמת דוח מנותחת מיד — זה המנוע העיקרי. סריקה מלאה על כל היקום רצה כרשת ביטחון כל ~80 יום."
                : "Checks daily at 07:30. Every company that reports is analyzed immediately — that's the primary engine. A full-universe sweep runs as a safety net every ~80 days."}
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
              onClick={handleRequeueReporters}
              disabled={batchStarting}
              className="text-xs bg-amber-700 hover:bg-amber-600 disabled:bg-gray-700 text-white px-3 py-1.5 rounded-lg"
              title={isHe ? "מחזיר לתור כל חברה שדיווחה ולא נותחה באמת (למשל בזמן נפילת מנוע)" : "Re-queue reporters that never got a real analysis"}
            >
              {batchStarting ? (isHe ? "בודק..." : "Checking...") : (isHe ? "נתח דוחות שלא נותחו" : "Re-queue reporters")}
            </button>
            <button
              onClick={handleRunQuarterlyBatch}
              disabled={batchStarting}
              className="text-xs bg-purple-700 hover:bg-purple-600 disabled:bg-gray-700 text-white px-3 py-1.5 rounded-lg"
              title={isHe ? "המשך את אצוות הסריקה הרבעונית של היום (אם נעצרה בפריסה)" : "Resume today's quarterly batch (if a deploy killed it)"}
            >
              {batchStarting ? (isHe ? "מפעיל..." : "Starting...") : (isHe ? "המשך סריקה רבעונית" : "Resume Quarterly Batch")}
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

        {batchResult && (
          <div className={`mb-4 p-3 rounded-xl text-xs ${batchResult.error ? "bg-red-900/20 text-red-400" : "bg-purple-900/20 text-purple-300"}`}>
            {batchResult.error
              ? batchResult.error
              : batchResult.started
                ? (isHe ? `האצווה רצה ברקע — ${batchResult.remaining_before} מניות בתור. עקוב ביומן הסריקות.` : `Batch running — ${batchResult.remaining_before} in queue. Watch the scan log.`)
                : (isHe ? `לא הופעל: ${batchResult.reason}${batchResult.remaining != null ? ` (בתור: ${batchResult.remaining})` : ""}` : `Not started: ${batchResult.reason}`)}
          </div>
        )}

        {/* Check result */}
        {earningsCheckResult && (
          <div className={`mb-4 p-3 rounded-xl text-xs ${earningsCheckResult.error ? "bg-red-900/20 text-red-400" : "bg-blue-900/20 text-blue-300"}`}>
            {earningsCheckResult.error ? earningsCheckResult.error : (
              earningsCheckResult.skipped
                ? (isHe ? `דולג: ${earningsCheckResult.reason}` : `Skipped: ${earningsCheckResult.reason}`)
                : (isHe
                    ? `נמצאו ${earningsCheckResult.past_confirmed ?? earningsCheckResult.fresh_this_run ?? 0} דוחות חדשים | סה"כ חברות שדיווחו הרבעון: ${earningsCheckResult.queued_total}`
                    : `Found ${earningsCheckResult.past_confirmed ?? earningsCheckResult.fresh_this_run ?? 0} new | Reporters this quarter: ${earningsCheckResult.queued_total}`)
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

            {/* Analysis progress. Previously this tracked reports collected
                against a 20-report trigger threshold — but that threshold was
                removed when earnings-driven analysis became the primary engine,
                so the bar measured progress toward something that no longer
                happens. What matters now is how many reporters were analysed. */}
            {(() => {
              const total = earningsStatus.queue_count ?? 0;
              const done = earningsStatus.analyzed_count ?? 0;
              const pct = total > 0 ? Math.round((done / total) * 100) : 0;
              return (
                <div className="mb-4">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-sm font-medium">
                      {isHe ? "דוחות שנותחו" : "Reporters analyzed"}
                    </span>
                    <span className="text-sm font-bold">
                      {done}
                      <span className="text-gray-500 font-normal"> / {total}</span>
                      <span className="text-gray-500 font-normal"> ({pct}%)</span>
                    </span>
                  </div>
                  <div className="w-full bg-gray-800 rounded-full h-2.5">
                    <div
                      className={`h-2.5 rounded-full transition-all ${
                        pct >= 95 ? "bg-green-500" : pct >= 60 ? "bg-blue-500" : "bg-amber-500"
                      }`}
                      style={{ width: `${Math.min(100, pct)}%` }}
                    />
                  </div>
                  {total > done && (
                    <p className="text-xs text-gray-500 mt-1">
                      {isHe
                        ? `${total - done} חברות שדיווחו עדיין ממתינות לניתוח`
                        : `${total - done} reporters still waiting for analysis`}
                    </p>
                  )}
                </div>
              );
            })()}

            {/* Status badge */}
            <div className="mb-4">
              {earningsStatus.scan_triggered ? (
                <div className="inline-flex items-center gap-2 bg-green-900/30 border border-green-800/50 rounded-lg px-3 py-1.5 text-xs text-green-300">
                  <span className="w-2 h-2 bg-green-400 rounded-full" />
                  {isHe
                    ? `סריקה רבעונית הושקה — ${earningsStatus.scan_triggered}`
                    : `Quarterly scan triggered — ${earningsStatus.scan_triggered}`}
                </div>
              ) : (
                <div className="inline-flex items-center gap-2 bg-gray-800 rounded-lg px-3 py-1.5 text-xs text-gray-400">
                  <span className="w-2 h-2 bg-gray-500 rounded-full" />
                  {isHe
                    ? "אין סריקה מלאה פעילה — דוחות חדשים מנותחים מיד עם פרסומם"
                    : "No full sweep running — new reports are analyzed as they arrive"}
                </div>
              )}
            </div>

            {/* Confirmed — already reported, with analysis status */}
            {earningsStatus.companies?.length > 0 && (
              <div className="mb-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs text-gray-500 uppercase tracking-wide">
                    {isHe ? "פרסמו דוחות — סטטוס ניתוח" : "Reported — analysis status"}
                  </p>
                  <p className="text-xs text-gray-400">
                    {isHe
                      ? `${earningsStatus.analyzed_count ?? 0}/${earningsStatus.companies.length} נותחו`
                      : `${earningsStatus.analyzed_count ?? 0}/${earningsStatus.companies.length} analyzed`}
                  </p>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5 max-h-56 overflow-y-auto pr-1">
                  {earningsStatus.companies.map((c: any) => {
                    const done = c.analyzed;
                    const badge = done
                      ? { txt: isHe ? "✓ נותחה" : "✓ analyzed", cls: "text-green-300 bg-green-900/30 border-green-800/40" }
                      : c.queued
                        ? { txt: isHe ? "⏳ בתור" : "⏳ queued", cls: "text-yellow-300 bg-yellow-900/20 border-yellow-800/40" }
                        : { txt: isHe ? "• ממתינה" : "• pending", cls: "text-gray-400 bg-gray-800/40 border-gray-700" };
                    return (
                      <div key={c.symbol} className={`flex items-center gap-2 rounded-lg px-2.5 py-1.5 border ${done ? "bg-green-900/10 border-green-900/30" : "bg-gray-800/30 border-gray-800"}`}>
                        <span className="font-mono font-bold text-xs text-white w-14">{c.symbol}</span>
                        <span className="text-xs text-gray-500">{c.earnings_date}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border ml-auto ${badge.cls}`}>{badge.txt}</span>
                      </div>
                    );
                  })}
                </div>
                <p className="text-[11px] text-gray-600 mt-1.5">
                  {isHe
                    ? "כל חברה שדיווחה מנותחת בסופו של דבר; המדווחות מקבלות עדיפות בתור. 'בתור' = ממתינה לניתוח בסבב הקרוב."
                    : "Every reporter is analyzed eventually; reporters get queue priority. 'queued' = awaiting analysis in an upcoming batch."}
                </p>
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
            {
              step: 6,
              icon: "🧠",
              title: isHe ? "בדיקת 3 מנועי ה-AI" : "AI Engines Check",
              desc: isHe
                ? `ניתוח אמיתי מלא של ${simSymbol} — מוודא ש-Claude, GPT (חדשות) ו-Gemini (מאקרו) כולם פועלים. לוקח 1-3 דקות ועולה ~10-25 סנט`
                : `Real full analysis of ${simSymbol} — verifies Claude, GPT (news) and Gemini (macro) all fire. Takes 1-3 min, costs ~$0.10-0.25`,
              action: async () => marketApi.simulateAiEnginesCheck(simSymbol),
            },
            {
              step: 7,
              icon: "🛠️",
              title: isHe ? "בדיקת ערוץ אדמין + תקציב" : "Admin Channel + Budget Check",
              desc: isHe
                ? "שולח הודעת בדיקה לערוץ האדמין ומציג את ההוצאה היומית המוערכת והתקרה"
                : "Sends a test message to the admin channel and shows today's estimated spend + cap",
              action: async () => marketApi.simulateTestAdminAlert(),
            },
            {
              step: 8,
              icon: "📡",
              title: isHe ? "בדיקת מקורות מחיר" : "Price Sources Check",
              desc: isHe
                ? `בודק אחד-אחד את Yahoo, Alpaca, FMP, Finnhub ו-Polygon על ${simSymbol} ומראה מי מחזיר מחיר. חינם ומיידי — בלי AI.`
                : `Probes Yahoo, Alpaca, FMP, Finnhub and Polygon one by one on ${simSymbol} and shows which return a price. Free and instant — no AI.`,
              action: async () => marketApi.checkPriceSources(simSymbol),
            },
            {
              step: 9,
              icon: "💾",
              title: isHe ? "הורד גיבוי מלא" : "Download Full Backup",
              desc: isHe
                ? "מוריד את כל הנתונים (קובץ CSV לכל טבלה, בתוך ZIP) למחשב שלך. Railway מספקת גיבויים רק במסלול Pro — זו רשת הביטחון בפועל. הרץ לפני כל שינוי במסד הנתונים."
                : "Downloads all data (one CSV per table, zipped) to your machine. Railway only offers backups on the Pro plan — this is the actual safety net. Run it before any database change.",
              action: async () => marketApi.downloadBackup(),
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
                  step === 8 && simStep[step].sources ? (
                    <div className="mt-2 space-y-1.5">
                      <p className="text-sm font-medium text-white">{simStep[step].verdict}</p>
                      {(simStep[step].sources as any[]).map((s) => (
                        <div
                          key={s.source}
                          className={`flex items-center gap-2 text-xs px-2 py-1 rounded ${
                            s.ok
                              ? "bg-green-900/20 text-green-300"
                              : s.configured
                              ? "bg-red-900/20 text-red-300"
                              : "bg-gray-800/60 text-gray-500"
                          }`}
                        >
                          <span>{s.ok ? "✅" : s.configured ? "❌" : "⚪"}</span>
                          <span className="font-medium whitespace-nowrap">{s.source}</span>
                          <span className="truncate">{s.detail}</span>
                          {!s.ok && s.hint && (
                            <span className="text-gray-500 whitespace-nowrap">· {s.hint}</span>
                          )}
                        </div>
                      ))}
                      <div
                        className={`text-xs px-2 py-1 rounded ${
                          simStep[step].batch_quotes?.ok
                            ? "bg-green-900/20 text-green-300"
                            : "bg-yellow-900/20 text-yellow-300"
                        }`}
                      >
                        {simStep[step].batch_quotes?.ok ? "✅" : "⚠️"}{" "}
                        {isHe ? "ציטוטים מרובים (פרה-סקרינר): " : "Batch quotes (screener): "}
                        {simStep[step].batch_quotes?.detail}
                      </div>
                    </div>
                  ) : step === 6 && simStep[step].engines ? (
                    <div className="mt-2 space-y-1.5">
                      {Object.entries(simStep[step].engines as Record<string, { ok: boolean; detail: string }>).map(([engine, res]) => {
                        const labels: Record<string, string> = {
                          claude: isHe ? "Claude — פונדמנטלי + ועדה" : "Claude — fundamental + senior",
                          openai_news: isHe ? "GPT — ניתוח חדשות" : "GPT — news analysis",
                          gemini_macro: isHe ? "Gemini — מאקרו" : "Gemini — macro",
                        };
                        return (
                          <div key={engine} className={`flex items-center gap-2 text-xs px-2 py-1 rounded ${res.ok ? "bg-green-900/20 text-green-300" : "bg-red-900/20 text-red-300"}`}>
                            <span>{res.ok ? "✅" : "❌"}</span>
                            <span className="font-medium whitespace-nowrap">{labels[engine] || engine}</span>
                            <span className="text-gray-400 truncate">{res.detail}</span>
                          </div>
                        );
                      })}
                      {simStep[step].news_sources && Object.keys(simStep[step].news_sources).length > 0 && (
                        <p className="text-xs text-cyan-400/80">
                          📰 {isHe ? "מקורות חדשות:" : "News sources:"}{" "}
                          {Object.entries(simStep[step].news_sources as Record<string, number>)
                            .map(([src, n]) => `${src} (${n})`).join(" · ")}
                          {" — "}{simStep[step].news_articles_total} {isHe ? "כתבות" : "articles"}
                        </p>
                      )}
                      {simStep[step].data_sources && (
                        <div className="mt-1 space-y-1">
                          <p className="text-xs text-gray-400 font-medium">{isHe ? "מקורות נתונים:" : "Data sources:"}</p>
                          {Object.entries(simStep[step].data_sources as Record<string, { ok: boolean; detail: string }>).map(([src, res]) => {
                            const srcLabels: Record<string, string> = {
                              price_fundamentals: isHe ? "מחיר + פונדמנטלס (Yahoo/TASE)" : "Price + fundamentals",
                              social_sentiment: isHe ? "סנטימנט רשתות" : "Social sentiment",
                              news: isHe ? "חדשות" : "News",
                              grok_x: isHe ? "Grok — סריקת X/טוויטר" : "Grok — X/Twitter scan",
                              insider_activity: isHe ? "עסקאות בעלי עניין" : "Insider activity",
                              sec_filings: isHe ? "דוחות SEC" : "SEC filings",
                            };
                            return (
                              <div key={src} className="flex items-center gap-2 text-xs px-2 py-0.5 rounded bg-gray-800/40 text-gray-300">
                                <span>{res.ok ? "✅" : "⚠️"}</span>
                                <span className="whitespace-nowrap">{srcLabels[src] || src}</span>
                                <span className="text-gray-500 truncate">{res.detail}</span>
                              </div>
                            );
                          })}
                          {simStep[step].fetch_errors?.length > 0 && (
                            <p className="text-xs text-red-400/80">⚠ {simStep[step].fetch_errors.join(" | ")}</p>
                          )}
                        </div>
                      )}
                      <p className="text-xs text-gray-500">
                        {simStep[step].workflow_status === "saved"
                          ? (isHe ? `נשמרה המלצה חדשה (#${simStep[step].recommendation_id})` : `New recommendation saved (#${simStep[step].recommendation_id})`)
                          : (isHe ? `סטטוס: ${simStep[step].workflow_status || "?"}${simStep[step].error ? " — " + simStep[step].error : ""}` : `Status: ${simStep[step].workflow_status || "?"}`)}
                      </p>
                    </div>
                  ) : step === 5 && simStep[step].diagnostics ? (
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
