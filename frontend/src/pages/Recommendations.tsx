import React, { useEffect, useState } from "react";
import { useAppDispatch, useAppSelector } from "../store";
import { fetchInbox, fetchRecommendations, markNotificationRead, acknowledgeRecommendation } from "../store/slices/notificationsSlice";
import { recommendationsApi, ordersApi } from "../api/client";
import { Recommendation, OrderType, TechnicalAnalysis } from "../types";
import RecommendationCard from "../components/Recommendations/RecommendationCard";
import AgentDecisionTree from "../components/Recommendations/AgentDecisionTree";
import ConfirmTradeModal from "../components/Trading/ConfirmTradeModal";

const Recommendations: React.FC = () => {
  const dispatch = useAppDispatch();
  const { user } = useAppSelector((state) => state.auth);
  const { notifications, recommendations, isLoading } = useAppSelector((state) => state.notifications);
  const isHe = user?.preferred_language === "he";

  const [view, setView] = useState<"inbox" | "recommendations">("inbox");
  const [selectedRec, setSelectedRec] = useState<Recommendation | null>(null);
  const [tradeModal, setTradeModal] = useState<{ rec: Recommendation; type: OrderType } | null>(null);
  const [technicalLoading, setTechnicalLoading] = useState<number | null>(null);
  const [technicalResults, setTechnicalResults] = useState<Record<number, TechnicalAnalysis>>({});

  useEffect(() => {
    dispatch(fetchInbox({ unreadOnly: false }));
    dispatch(fetchRecommendations({}));
  }, [dispatch]);

  const handleReadNotification = (id: number) => {
    dispatch(markNotificationRead(id));
  };

  const handleAcknowledge = (recId: number) => {
    dispatch(acknowledgeRecommendation(recId));
    setSelectedRec(null);
  };

  const handleRequestTechnical = async (recId: number) => {
    setTechnicalLoading(recId);
    try {
      const result = await recommendationsApi.requestTechnicalAnalysis(recId);
      if (result.technical_analysis) {
        setTechnicalResults({ ...technicalResults, [recId]: result.technical_analysis });
      }
    } catch (e) {
      console.error("Technical analysis failed", e);
    }
    setTechnicalLoading(null);
  };

  const handleTrade = async (rec: Recommendation, orderType: OrderType) => {
    setTradeModal({ rec, type: orderType });
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

  const signalColor = (signal?: string) => {
    if (!signal) return "text-gray-400";
    if (signal.includes("BUY")) return "text-green-400";
    if (signal.includes("SELL")) return "text-red-400";
    return "text-yellow-400";
  };

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{isHe ? "המלצות ועדכונים" : "Recommendations & Updates"}</h1>
      </div>

      {/* Tabs */}
      <div className="flex bg-gray-900 rounded-xl p-1 w-fit">
        <button
          onClick={() => setView("inbox")}
          className={`px-6 py-2 rounded-lg text-sm font-medium transition-colors ${view === "inbox" ? "bg-blue-600 text-white" : "text-gray-400"}`}
        >
          {isHe ? "תיבת דואר" : "Inbox"}
          {notifications.filter((n) => !n.is_read).length > 0 && (
            <span className="ml-2 bg-red-500 text-xs rounded-full px-1.5 py-0.5">
              {notifications.filter((n) => !n.is_read).length}
            </span>
          )}
        </button>
        <button
          onClick={() => setView("recommendations")}
          className={`px-6 py-2 rounded-lg text-sm font-medium transition-colors ${view === "recommendations" ? "bg-blue-600 text-white" : "text-gray-400"}`}
        >
          {isHe ? "המלצות AI" : "AI Recommendations"}
        </button>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 bg-gray-900 rounded-2xl animate-pulse" />
          ))}
        </div>
      )}

      {/* Inbox View */}
      {view === "inbox" && !isLoading && (
        <div className="space-y-3">
          {notifications.length === 0 ? (
            <div className="bg-gray-900 rounded-2xl p-12 border border-gray-800 text-center text-gray-500">
              <p className="text-4xl mb-3">📬</p>
              <p>{isHe ? "תיבת הדואר ריקה" : "Inbox is empty"}</p>
            </div>
          ) : (
            notifications.map((notif) => (
              <div
                key={notif.id}
                className={`bg-gray-900 rounded-2xl p-5 border cursor-pointer transition-colors ${
                  !notif.is_read ? "border-blue-700/50 hover:border-blue-600" : "border-gray-800 hover:border-gray-700"
                }`}
                onClick={() => {
                  handleReadNotification(notif.id);
                  if (notif.recommendation_id) {
                    const rec = recommendations.find((r) => r.id === notif.recommendation_id);
                    if (rec) setSelectedRec(rec);
                  }
                }}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      {!notif.is_read && (
                        <span className="w-2 h-2 bg-blue-400 rounded-full flex-shrink-0" />
                      )}
                      <p className="font-medium text-sm">
                        {notif.title || (isHe ? "עדכון השקעות" : "Investment Update")}
                      </p>
                    </div>
                    {/* Full internal detail visible to authenticated users */}
                    {notif.internal_detail && (
                      <div className="mt-2 space-y-1">
                        {notif.internal_detail.symbol && (
                          <p className="text-xs text-gray-400">
                            <span className="font-bold text-white">{notif.internal_detail.symbol}</span>
                            {notif.internal_detail.recommendation_type && (
                              <span className={`ml-2 font-medium ${
                                notif.internal_detail.recommendation_type.includes("BUY") ? "text-green-400" :
                                notif.internal_detail.recommendation_type.includes("SELL") ? "text-red-400" : "text-yellow-400"
                              }`}>
                                {notif.internal_detail.recommendation_type}
                              </span>
                            )}
                          </p>
                        )}
                        {notif.internal_detail.confidence_score && (
                          <p className="text-xs text-gray-400">
                            {isHe ? "ביטחון:" : "Confidence:"} {notif.internal_detail.confidence_score.toFixed(0)}%
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 flex-shrink-0">
                    {new Date(notif.sent_at).toLocaleString(isHe ? "he-IL" : "en-US")}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Recommendations View */}
      {view === "recommendations" && !isLoading && (
        <div className="space-y-4">
          {recommendations.length === 0 ? (
            <div className="bg-gray-900 rounded-2xl p-12 border border-gray-800 text-center text-gray-500">
              <p className="text-4xl mb-3">🤖</p>
              <p>{isHe ? "אין המלצות חדשות" : "No new recommendations"}</p>
              <p className="text-sm mt-1">{isHe ? "הסוכנים סורקים את השוק 24/7" : "Agents are scanning markets 24/7"}</p>
            </div>
          ) : (
            recommendations.map((rec) => (
              <RecommendationCard
                key={rec.id}
                recommendation={rec}
                isHe={isHe}
                technicalAnalysis={technicalResults[rec.id]}
                isLoadingTechnical={technicalLoading === rec.id}
                onRequestTechnical={() => handleRequestTechnical(rec.id)}
                onBuy={() => handleTrade(rec, OrderType.BUY)}
                onSell={() => handleTrade(rec, OrderType.SELL)}
                onDismiss={() => handleAcknowledge(rec.id)}
              />
            ))
          )}
        </div>
      )}

      {/* Detailed Recommendation Panel */}
      {selectedRec && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" onClick={() => setSelectedRec(null)}>
          <div
            className="bg-gray-900 rounded-2xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto border border-gray-700"
            onClick={(e) => e.stopPropagation()}
            dir={isHe ? "rtl" : "ltr"}
          >
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold">
                {selectedRec.symbol} - {selectedRec.recommendation_type}
              </h2>
              <button onClick={() => setSelectedRec(null)} className="text-gray-400 hover:text-white">✕</button>
            </div>

            <AgentDecisionTree
              symbol={selectedRec.symbol}
              hasFundamental={!!selectedRec.fundamental_analysis}
              hasSenior={!!selectedRec.senior_notes}
              hasTechnical={!!selectedRec.technical_analysis}
              isHe={isHe}
            />

            {selectedRec.fundamental_analysis && (
              <div className="mt-4 p-4 bg-gray-800 rounded-xl">
                <p className="text-sm font-bold mb-2">{isHe ? "ניתוח בסיסי" : "Fundamental Analysis"}</p>
                <p className="text-xs text-gray-300">{selectedRec.fundamental_analysis.bull_case}</p>
              </div>
            )}

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => handleTrade(selectedRec, OrderType.BUY)}
                className="flex-1 bg-green-600 hover:bg-green-700 text-white rounded-xl py-2.5 text-sm font-medium"
              >
                {isHe ? "קנייה" : "Buy"}
              </button>
              <button
                onClick={() => handleAcknowledge(selectedRec.id)}
                className="flex-1 border border-gray-700 text-gray-400 rounded-xl py-2.5 text-sm"
              >
                {isHe ? "התעלם" : "Dismiss"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Trade Confirmation Modal */}
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
