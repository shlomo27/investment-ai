import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../store";
import {
  fetchInbox,
  fetchRecommendations,
  markNotificationRead,
  acknowledgeRecommendation,
} from "../store/slices/notificationsSlice";
import { fetchPortfolioSummary } from "../store/slices/portfolioSlice";
import { recommendationsApi, ordersApi } from "../api/client";
import { Recommendation, OrderType, RecommendationType, TechnicalAnalysis } from "../types";
import ConfirmTradeModal from "../components/Trading/ConfirmTradeModal";
import RecommendationCard from "../components/Recommendations/RecommendationCard";

type DirectionFilter = "ALL" | "LONG" | "SHORT";

const recBadgeClass = (type: string) => {
  if (type === "STRONG_BUY") return "bg-green-500/20 text-green-300 border border-green-600/40";
  if (type === "BUY") return "bg-green-900/30 text-green-400 border border-green-700/40";
  if (type === "STRONG_SELL") return "bg-red-500/20 text-red-300 border border-red-600/40";
  if (type === "SELL") return "bg-red-900/30 text-red-400 border border-red-700/40";
  return "bg-gray-800 text-gray-400 border border-gray-700";
};

const isLong = (type: RecommendationType) =>
  type === RecommendationType.BUY || type === RecommendationType.STRONG_BUY;

const isShort = (type: RecommendationType) =>
  type === RecommendationType.SELL || type === RecommendationType.STRONG_SELL;

const Recommendations: React.FC = () => {
  const dispatch = useAppDispatch();
  const { user } = useAppSelector((s) => s.auth);
  const { notifications, recommendations, isLoading } = useAppSelector(
    (s) => s.notifications
  );
  const { summary: portfolioSummary } = useAppSelector((s) => s.portfolio);
  const isHe = user?.preferred_language === "he";

  const [view, setView] = useState<"inbox" | "signals" | "scanlog">("inbox");
  const [scanLog, setScanLog] = useState<Awaited<ReturnType<typeof recommendationsApi.getScanActivity>> | null>(null);
  const [scanLogLoading, setScanLogLoading] = useState(false);
  const [expandedLog, setExpandedLog] = useState<number | null>(null);
  const [expandedNotif, setExpandedNotif] = useState<number | null>(null);

  useEffect(() => {
    if (view !== "scanlog" || scanLog) return;
    setScanLogLoading(true);
    recommendationsApi.getScanActivity(7)
      .then(setScanLog)
      .catch(() => {})
      .finally(() => setScanLogLoading(false));
  }, [view]);
  const [dirFilter, setDirFilter] = useState<DirectionFilter>("ALL");
  const [tradeModal, setTradeModal] = useState<{ rec: Recommendation; type: OrderType } | null>(null);
  const [techMap, setTechMap] = useState<Record<number, TechnicalAnalysis>>({});
  const [loadingTech, setLoadingTech] = useState<Record<number, boolean>>({});

  useEffect(() => {
    dispatch(fetchInbox({ unreadOnly: false }));
    dispatch(fetchRecommendations({}));
    dispatch(fetchPortfolioSummary()); // needed for suggested investment amounts
  }, [dispatch]);

  const handleReadNotification = (id: number) => {
    dispatch(markNotificationRead(id));
  };

  const handleAcknowledge = (recId: number) => {
    dispatch(acknowledgeRecommendation(recId));
  };

  const handleRequestTechnical = async (recId: number) => {
    setLoadingTech((prev) => ({ ...prev, [recId]: true }));
    try {
      const result = await recommendationsApi.requestTechnicalAnalysis(recId);
      setTechMap((prev) => ({ ...prev, [recId]: result.technical_analysis }));
    } catch {
      // silently fail — tech analysis is optional
    } finally {
      setLoadingTech((prev) => ({ ...prev, [recId]: false }));
    }
  };

  const getSuggestedAmount = (rec: Recommendation): number | undefined => {
    if (!portfolioSummary?.total_value) return undefined;
    const alloc = (rec.fundamental_analysis as any)?.allocation_recommendation;
    const pct = alloc === "HIGH" ? 0.15 : alloc === "MEDIUM" ? 0.10 : 0.05;
    return portfolioSummary.total_value * pct;
  };

  const handleConfirmTrade = async (quantity: number, price: number) => {
    if (!tradeModal) return;
    try {
      await ordersApi.createOrder({
        symbol: tradeModal.rec.symbol,
        order_type: tradeModal.type,
        quantity,
        price,
        recommendation_id: tradeModal.rec.id,
      });
      // NOTE: deliberately NOT acknowledging — a holder needs continued access
      // to the recommendation's analysis in the signals feed. Explicit
      // "Dismiss" remains available on the card.
      setTradeModal(null);
    } catch (e: any) {
      alert(e.response?.data?.detail || "Order failed");
    }
  };

  const BUY_LIMIT = 20;
  const SELL_LIMIT = 10;

  // Sort all recommendations by confidence DESC
  const sorted = [...recommendations].sort((a, b) => b.confidence_score - a.confidence_score);

  // Top 20 BUY + top 10 SELL (by confidence)
  const topBuys = sorted.filter((r) => isLong(r.recommendation_type)).slice(0, BUY_LIMIT);
  const topSells = sorted.filter((r) => isShort(r.recommendation_type)).slice(0, SELL_LIMIT);
  const topPicks = [...topBuys, ...topSells].sort((a, b) => b.confidence_score - a.confidence_score);

  const filteredRecs =
    dirFilter === "LONG" ? topBuys :
    dirFilter === "SHORT" ? topSells :
    topPicks;

  const unreadCount = notifications.filter((n) => !n.is_read).length;
  const longCount = topBuys.length;
  const shortCount = topSells.length;

  const getTriggerBadge = (triggerType?: string) => {
    if (triggerType === "PRICE_ALERT") return { label: isHe ? "מחיר" : "Price", cls: "bg-orange-900/40 text-orange-300" };
    if (triggerType === "NEWS_ALERT") return { label: isHe ? "חדשות" : "News", cls: "bg-purple-900/40 text-purple-300" };
    if (triggerType === "EARNINGS") return { label: isHe ? "דוח" : "Earnings", cls: "bg-blue-900/40 text-blue-300" };
    return null;
  };

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{isHe ? "סיגנלים והמלצות AI" : "AI Signals & Recommendations"}</h1>
        <Link to="/fund" className="text-xs text-gray-400 hover:text-gray-200">
          {isHe ? "לוח ניהול ←" : "Dashboard →"}
        </Link>
      </div>

      {/* Main Tabs */}
      <div className="flex bg-gray-900 rounded-xl p-1 w-fit">
        <button
          onClick={() => setView("inbox")}
          className={`px-5 py-2 rounded-lg text-sm font-medium transition-colors ${view === "inbox" ? "bg-blue-600 text-white" : "text-gray-400 hover:text-white"}`}
        >
          {isHe ? "תיבת דואר" : "Inbox"}
          {unreadCount > 0 && (
            <span className="ml-2 bg-red-500 text-xs rounded-full px-1.5 py-0.5">{unreadCount}</span>
          )}
        </button>
        <button
          onClick={() => setView("signals")}
          className={`px-5 py-2 rounded-lg text-sm font-medium transition-colors ${view === "signals" ? "bg-blue-600 text-white" : "text-gray-400 hover:text-white"}`}
        >
          {isHe ? "סיגנלים AI" : "AI Signals"}
          {topPicks.length > 0 && (
            <span className="ml-2 bg-gray-700 text-gray-300 text-xs rounded-full px-1.5 py-0.5">
              {topPicks.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setView("scanlog")}
          className={`px-5 py-2 rounded-lg text-sm font-medium transition-colors ${view === "scanlog" ? "bg-blue-600 text-white" : "text-gray-400 hover:text-white"}`}
        >
          {isHe ? "יומן סריקות" : "Scan Log"}
        </button>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 bg-gray-900 rounded-2xl animate-pulse" />
          ))}
        </div>
      )}

      {/* ── Scan Log ── */}
      {view === "scanlog" && !isLoading && (
        <div className="space-y-4">
          <p className="text-sm text-gray-400">
            {isHe
              ? "כל ניתוח שהמערכת הריצה ב-7 הימים האחרונים — כולל מניות שנבדקו ונדחו והנימוק של ועדת ההשקעות."
              : "Every analysis the system ran in the last 7 days — including stocks that were reviewed and rejected, with the committee's reasoning."}
          </p>

          {scanLogLoading && (
            <div className="h-24 bg-gray-900 rounded-2xl animate-pulse" />
          )}

          {!scanLogLoading && scanLog && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                {[
                  { key: "approved_buy", he: "אושרו — קנייה", en: "Approved BUY", cls: "text-green-400 border-green-900/50" },
                  { key: "approved_sell", he: "אושרו — מכירה", en: "Approved SELL", cls: "text-red-400 border-red-900/50" },
                  { key: "hold", he: "החזק", en: "HOLD", cls: "text-yellow-400 border-yellow-900/50" },
                  { key: "rejected", he: "נדחו", en: "Rejected", cls: "text-gray-300 border-gray-700" },
                  { key: "superseded", he: "הוחלפו", en: "Superseded", cls: "text-gray-500 border-gray-800" },
                ].map((c) => (
                  <div key={c.key} className={`bg-gray-900 border rounded-xl p-3 text-center ${c.cls}`}>
                    <p className="text-2xl font-bold">{scanLog.counts[c.key] || 0}</p>
                    <p className="text-xs mt-1">{isHe ? c.he : c.en}</p>
                  </div>
                ))}
              </div>

              {scanLog.items.length === 0 ? (
                <div className="bg-gray-900 rounded-2xl p-12 border border-gray-800 text-center text-gray-500">
                  <p className="text-4xl mb-3">🔍</p>
                  <p>{isHe ? "לא רצו ניתוחים בתקופה זו" : "No analyses in this period"}</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {scanLog.items.map((item) => {
                    const badge =
                      item.bucket === "approved_buy" ? { txt: isHe ? "אושרה — קנייה" : "BUY", cls: "bg-green-900/40 text-green-300" } :
                      item.bucket === "approved_sell" ? { txt: isHe ? "אושרה — מכירה" : "SELL", cls: "bg-red-900/40 text-red-300" } :
                      item.bucket === "hold" ? { txt: isHe ? "החזק" : "HOLD", cls: "bg-yellow-900/30 text-yellow-300" } :
                      item.bucket === "superseded" ? { txt: isHe ? "הוחלפה" : "Superseded", cls: "bg-gray-800 text-gray-500" } :
                      { txt: isHe ? "נדחתה" : "Rejected", cls: "bg-gray-800 text-gray-400 border border-gray-700" };
                    const canOpenReport = item.bucket !== "rejected";
                    return (
                      <div key={item.id} className="bg-gray-900 rounded-xl border border-gray-800 px-4 py-3">
                        <div className="flex items-center gap-3">
                          <span className="font-mono font-bold text-sm w-16">{item.symbol}</span>
                          <span className={`text-xs rounded-full px-2 py-0.5 ${badge.cls}`}>{badge.txt}</span>
                          <span className="text-xs text-gray-500">
                            {item.confidence_score ? `${Math.round(item.confidence_score)}%` : ""}
                          </span>
                          <div className="flex-1" />
                          <span className="text-xs text-gray-600">
                            {item.created_at ? new Date(item.created_at).toLocaleDateString(isHe ? "he-IL" : "en-US") : ""}
                          </span>
                          {item.reason && (
                            <button
                              onClick={() => setExpandedLog(expandedLog === item.id ? null : item.id)}
                              className="text-xs text-gray-400 hover:text-white border border-gray-700 rounded-lg px-2 py-1"
                            >
                              {expandedLog === item.id ? (isHe ? "הסתר" : "Hide") : (isHe ? "נימוק" : "Why")}
                            </button>
                          )}
                          {canOpenReport && (
                            <Link
                              to={`/research/${item.id}`}
                              className="text-xs text-yellow-400 hover:text-yellow-300 border border-yellow-800/50 rounded-lg px-2 py-1"
                            >
                              {isHe ? "דוח" : "Report"}
                            </Link>
                          )}
                        </div>
                        {expandedLog === item.id && item.reason && (
                          <p className="text-xs text-gray-400 mt-2 pt-2 border-t border-gray-800 leading-relaxed">
                            {item.reason}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Inbox ── */}
      {view === "inbox" && !isLoading && (
        <div className="space-y-3">
          {notifications.length === 0 ? (
            <div className="bg-gray-900 rounded-2xl p-12 border border-gray-800 text-center text-gray-500">
              <p className="text-4xl mb-3">📬</p>
              <p>{isHe ? "תיבת הדואר ריקה" : "Inbox is empty"}</p>
            </div>
          ) : (
            notifications.map((notif) => {
              const trigger = getTriggerBadge(notif.internal_detail?.trigger_type);
              const sym = notif.internal_detail?.symbol;
              const recType = notif.internal_detail?.recommendation_type as string | undefined;
              const recId = notif.recommendation_id;

              return (
                <div
                  key={notif.id}
                  onClick={() => {
                    handleReadNotification(notif.id);
                    setExpandedNotif((prev) => (prev === notif.id ? null : notif.id));
                  }}
                  className={`bg-gray-900 rounded-2xl p-5 border cursor-pointer transition-colors ${
                    !notif.is_read ? "border-blue-700/50 hover:border-blue-600" : "border-gray-800 hover:border-gray-700"
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-2">
                        {!notif.is_read && (
                          <span className="w-2 h-2 bg-blue-400 rounded-full flex-shrink-0" />
                        )}
                        {trigger && (
                          <span className={`text-xs px-1.5 py-0.5 rounded ${trigger.cls}`}>
                            {trigger.label}
                          </span>
                        )}
                        {sym && (
                          <span className="font-mono font-bold text-white">{sym}</span>
                        )}
                        {recType && (
                          <span className={`text-xs px-2 py-0.5 rounded border ${recBadgeClass(recType)}`}>
                            {recType.replace("_", " ")}
                          </span>
                        )}
                      </div>
                      <p className={`text-sm text-gray-300 ${expandedNotif === notif.id ? "" : "truncate"}`}>
                        {notif.title || notif.external_message}
                      </p>
                      {notif.internal_detail?.confidence_score && (
                        <p className="text-xs text-gray-500 mt-1">
                          {isHe ? "ביטחון:" : "Confidence:"}{" "}
                          {notif.internal_detail.confidence_score.toFixed(0)}%
                        </p>
                      )}
                      {expandedNotif === notif.id && notif.internal_detail && (
                        <div className="mt-3 pt-3 border-t border-gray-800 space-y-2 text-xs text-gray-400">
                          {notif.internal_detail.news_summary && (
                            <p>
                              <span className="text-gray-500 font-medium">{isHe ? "סיכום החדשות: " : "News summary: "}</span>
                              {notif.internal_detail.news_summary}
                            </p>
                          )}
                          {(notif.internal_detail.signal || notif.internal_detail.ta_signal) && (
                            <p>
                              <span className="text-gray-500 font-medium">{isHe ? "מצב טכני: " : "Technical: "}</span>
                              {notif.internal_detail.signal || notif.internal_detail.ta_signal}
                              {notif.internal_detail.previous_signal ? ` (${isHe ? "קודם" : "prev"}: ${notif.internal_detail.previous_signal})` : ""}
                              {(notif.internal_detail.technical_score ?? notif.internal_detail.ta_score) != null
                                ? ` · ${isHe ? "ציון" : "score"} ${Math.round(notif.internal_detail.technical_score ?? notif.internal_detail.ta_score)}/100`
                                : ""}
                              {notif.internal_detail.current_price ? ` · $${Number(notif.internal_detail.current_price).toFixed(2)}` : ""}
                            </p>
                          )}
                          {notif.internal_detail.x_buzz_posts > 0 && (
                            <p>
                              <span className="text-gray-500 font-medium">{isHe ? "רשת X: " : "X buzz: "}</span>
                              {notif.internal_detail.x_buzz_posts} {isHe ? "פוסטים, סנטימנט" : "posts, sentiment"}{" "}
                              {Number(notif.internal_detail.x_buzz_score).toFixed(2)}
                            </p>
                          )}
                          {notif.internal_detail.senior_notes && (
                            <p>
                              <span className="text-gray-500 font-medium">{isHe ? "הערות הוועדה: " : "Committee: "}</span>
                              {notif.internal_detail.senior_notes}
                            </p>
                          )}
                          {Array.isArray(notif.internal_detail.articles) && notif.internal_detail.articles.length > 0 && (
                            <div>
                              <p className="text-gray-500 font-medium mb-1">{isHe ? "כתבות:" : "Articles:"}</p>
                              <ul className="space-y-1">
                                {notif.internal_detail.articles.map((a: any, i: number) => (
                                  <li key={i}>
                                    {a.url ? (
                                      <a
                                        href={a.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        onClick={(e) => e.stopPropagation()}
                                        className="text-blue-400 hover:text-blue-300 underline"
                                      >
                                        {a.title}
                                      </a>
                                    ) : (
                                      <span>{a.title}</span>
                                    )}
                                    {a.source ? <span className="text-gray-600"> — {a.source}</span> : null}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-2 flex-shrink-0">
                      <p className="text-xs text-gray-500">
                        {new Date(notif.sent_at).toLocaleString(isHe ? "he-IL" : "en-US")}
                      </p>
                      {recId && (
                        <Link
                          to={`/research/${recId}`}
                          onClick={(e) => e.stopPropagation()}
                          className="text-xs text-blue-400 hover:text-blue-300 px-2 py-1 border border-blue-800 rounded-lg"
                        >
                          {isHe ? "דוח מחקר →" : "Research →"}
                        </Link>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* ── AI Signals ── */}
      {view === "signals" && !isLoading && (
        <div className="space-y-4">
          {/* Direction Filter */}
          <div className="flex items-center gap-2">
            {(["ALL", "LONG", "SHORT"] as DirectionFilter[]).map((f) => (
              <button
                key={f}
                onClick={() => setDirFilter(f)}
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors border ${
                  dirFilter === f
                    ? f === "LONG" ? "bg-green-900/40 text-green-300 border-green-700/40"
                    : f === "SHORT" ? "bg-red-900/40 text-red-300 border-red-700/40"
                    : "bg-blue-700 text-white border-blue-600"
                    : "bg-gray-900 text-gray-400 border-gray-800 hover:border-gray-600"
                }`}
              >
                {f === "LONG" ? `LONG (${longCount})` : f === "SHORT" ? `SHORT (${shortCount})` : `${isHe ? "הכל" : "All"} (${topPicks.length})`}
              </button>
            ))}
          </div>

          {filteredRecs.length === 0 ? (
            <div className="bg-gray-900 rounded-2xl p-12 border border-gray-800 text-center text-gray-500">
              <p className="text-4xl mb-3">🤖</p>
              <p>{isHe ? "אין סיגנלים בפילטר זה" : "No signals for this filter"}</p>
              <p className="text-sm mt-1">{isHe ? "הסוכנים סורקים את השוק" : "Agents are scanning markets"}</p>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredRecs.map((rec) => (
                <RecommendationCard
                  key={rec.id}
                  recommendation={rec}
                  isHe={isHe}
                  technicalAnalysis={techMap[rec.id]}
                  isLoadingTechnical={!!loadingTech[rec.id]}
                  onRequestTechnical={() => handleRequestTechnical(rec.id)}
                  onBuy={() => setTradeModal({ rec, type: OrderType.BUY })}
                  onSell={() => setTradeModal({ rec, type: OrderType.SELL })}
                  onDismiss={() => handleAcknowledge(rec.id)}
                  suggestedAmount={getSuggestedAmount(rec)}
                  approvedAt={rec.approved_at}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {tradeModal && (
        <ConfirmTradeModal
          recommendation={tradeModal.rec}
          orderType={tradeModal.type}
          isHe={isHe}
          onConfirm={handleConfirmTrade}
          onCancel={() => setTradeModal(null)}
        />
      )}
    </div>
  );
};

export default Recommendations;
