import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../store";
import {
  fetchInbox,
  fetchRecommendations,
  markNotificationRead,
  acknowledgeRecommendation,
} from "../store/slices/notificationsSlice";
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

  const [view, setView] = useState<"inbox" | "signals">("inbox");
  const [dirFilter, setDirFilter] = useState<DirectionFilter>("ALL");
  const [tradeModal, setTradeModal] = useState<{ rec: Recommendation; type: OrderType } | null>(null);
  const [techMap, setTechMap] = useState<Record<number, TechnicalAnalysis>>({});
  const [loadingTech, setLoadingTech] = useState<Record<number, boolean>>({});

  useEffect(() => {
    dispatch(fetchInbox({ unreadOnly: false }));
    dispatch(fetchRecommendations({}));
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
      dispatch(acknowledgeRecommendation(tradeModal.rec.id));
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
          {isHe ? "לוח קרן ←" : "Fund Dashboard →"}
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
          {recommendations.length > 0 && (
            <span className="ml-2 bg-gray-700 text-gray-300 text-xs rounded-full px-1.5 py-0.5">
              {recommendations.length}
            </span>
          )}
        </button>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 bg-gray-900 rounded-2xl animate-pulse" />
          ))}
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
                      <p className="text-sm text-gray-300 truncate">
                        {notif.title || notif.external_message}
                      </p>
                      {notif.internal_detail?.confidence_score && (
                        <p className="text-xs text-gray-500 mt-1">
                          {isHe ? "ביטחון:" : "Confidence:"}{" "}
                          {notif.internal_detail.confidence_score.toFixed(0)}%
                        </p>
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
                {f === "LONG" ? `LONG (${longCount})` : f === "SHORT" ? `SHORT (${shortCount})` : `${isHe ? "הכל" : "All"} (${recommendations.length})`}
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
