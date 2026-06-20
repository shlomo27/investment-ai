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
import { Recommendation, OrderType, RecommendationType } from "../types";
import ConfirmTradeModal from "../components/Trading/ConfirmTradeModal";

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
  const isHe = user?.preferred_language === "he";

  const [view, setView] = useState<"inbox" | "signals">("inbox");
  const [dirFilter, setDirFilter] = useState<DirectionFilter>("ALL");
  const [tradeModal, setTradeModal] = useState<{ rec: Recommendation; type: OrderType } | null>(null);

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

  const filteredRecs = recommendations.filter((r) => {
    if (dirFilter === "LONG") return isLong(r.recommendation_type);
    if (dirFilter === "SHORT") return isShort(r.recommendation_type);
    return true;
  });

  const unreadCount = notifications.filter((n) => !n.is_read).length;
  const longCount = recommendations.filter((r) => isLong(r.recommendation_type)).length;
  const shortCount = recommendations.filter((r) => isShort(r.recommendation_type)).length;

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
              {filteredRecs.map((rec) => {
                const long = isLong(rec.recommendation_type);
                const short = isShort(rec.recommendation_type);
                const fa = rec.fundamental_analysis;
                const trigger = getTriggerBadge(rec.trigger_type);
                const returnPct = rec.expected_return_pct ?? fa?.expected_return_pct;

                return (
                  <div
                    key={rec.id}
                    className={`bg-gray-900 rounded-2xl p-5 border transition-colors hover:border-gray-600 ${
                      long ? "border-green-900/40" : short ? "border-red-900/40" : "border-gray-800"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        {/* Symbol + badges */}
                        <div className="flex items-center gap-2 flex-wrap mb-2">
                          <span className="font-mono font-bold text-lg">{rec.symbol}</span>
                          <span className={`text-xs px-2 py-0.5 rounded border ${recBadgeClass(rec.recommendation_type)}`}>
                            {rec.recommendation_type.replace("_", " ")}
                          </span>
                          {fa?.direction_bias && fa.direction_bias !== "NEUTRAL" && (
                            <span className={`text-xs px-1.5 py-0.5 rounded ${
                              fa.direction_bias === "LONG" ? "bg-green-900/30 text-green-400" : "bg-red-900/30 text-red-400"
                            }`}>
                              {fa.direction_bias}
                            </span>
                          )}
                          {trigger && (
                            <span className={`text-xs px-1.5 py-0.5 rounded ${trigger.cls}`}>
                              {trigger.label}
                            </span>
                          )}
                        </div>

                        {/* Thesis or asset name */}
                        {fa?.thesis ? (
                          <p className="text-sm text-gray-300 line-clamp-2">{fa.thesis}</p>
                        ) : rec.asset_name ? (
                          <p className="text-sm text-gray-400">{rec.asset_name}</p>
                        ) : null}

                        {/* Key numbers */}
                        <div className="flex items-center gap-4 mt-2 text-xs text-gray-400">
                          <span>{isHe ? "ביטחון:" : "Conf:"} <span className="text-white font-medium">{rec.confidence_score.toFixed(0)}%</span></span>
                          {rec.target_price && (
                            <span>{isHe ? "יעד:" : "Target:"} <span className="text-white font-medium">${rec.target_price.toFixed(2)}</span></span>
                          )}
                          {rec.stop_loss && (
                            <span>Stop: <span className="text-white font-medium">${rec.stop_loss.toFixed(2)}</span></span>
                          )}
                          {returnPct != null && (
                            <span className={returnPct >= 0 ? "text-green-400" : "text-red-400"}>
                              {returnPct >= 0 ? "+" : ""}{returnPct.toFixed(1)}%
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex flex-col items-end gap-2 flex-shrink-0">
                        <Link
                          to={`/research/${rec.id}`}
                          className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded-lg"
                        >
                          {isHe ? "דוח מחקר" : "Research"}
                        </Link>
                        {long && (
                          <button
                            onClick={() => setTradeModal({ rec, type: OrderType.BUY })}
                            className="text-xs bg-green-700 hover:bg-green-600 text-white px-3 py-1.5 rounded-lg"
                          >
                            {isHe ? "קנה" : "Buy"}
                          </button>
                        )}
                        {short && (
                          <button
                            onClick={() => setTradeModal({ rec, type: OrderType.SELL })}
                            className="text-xs bg-red-700 hover:bg-red-600 text-white px-3 py-1.5 rounded-lg"
                          >
                            Short
                          </button>
                        )}
                        <button
                          onClick={() => handleAcknowledge(rec.id)}
                          className="text-xs text-gray-500 hover:text-gray-300"
                        >
                          {isHe ? "התעלם" : "Dismiss"}
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
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
