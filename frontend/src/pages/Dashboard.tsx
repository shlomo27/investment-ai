import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../store";
import { fetchPortfolioSummary } from "../store/slices/portfolioSlice";
import { fetchInbox, fetchUnreadCount, fetchRecommendations } from "../store/slices/notificationsSlice";
import { performanceApi } from "../api/client";

const Dashboard: React.FC = () => {
  const dispatch = useAppDispatch();
  const { user } = useAppSelector((state) => state.auth);
  const { summary, isLoading: portfolioLoading } = useAppSelector((state) => state.portfolio);
  const { notifications, unreadCount, recommendations } = useAppSelector((state) => state.notifications);

  const isHe = user?.preferred_language === "he";

  useEffect(() => {
    dispatch(fetchPortfolioSummary());
    dispatch(fetchInbox({ unreadOnly: false }));
    dispatch(fetchRecommendations({}));
  }, [dispatch]);

  const formatCurrency = (value: number, currency = "₪") =>
    `${currency}${Math.abs(value).toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const pnlPositive = (summary?.total_pnl || 0) >= 0;

  const riskColors: Record<string, string> = {
    CONSERVATIVE: "text-green-400",
    PASSIVE: "text-blue-400",
    HYBRID: "text-yellow-400",
    AGGRESSIVE: "text-red-400",
  };

  const riskLabels: Record<string, { he: string; en: string }> = {
    CONSERVATIVE: { he: "שמרני", en: "Conservative" },
    PASSIVE: { he: "פסיבי", en: "Passive" },
    HYBRID: { he: "סיכון בינוני", en: "Medium Risk" },
    AGGRESSIVE: { he: "סיכון גבוה", en: "High Risk" },
  };

  const investmentTypeLabel: Record<string, { he: string; en: string; icon: string }> = {
    STOCKS: { he: "מניות בלבד", en: "Stocks Only", icon: "📈" },
    ETFS: { he: "ETF בלבד", en: "ETFs Only", icon: "🗂️" },
    BOTH: { he: "מניות + ETF", en: "Stocks + ETFs", icon: "🔀" },
  };

  const getTriggerBadge = (notif: any) => {
    const trigger = notif.internal_detail?.trigger_type;
    if (trigger === "PRICE_ALERT") return { label: isHe ? "תנועת מחיר" : "Price Alert", color: "bg-orange-900/50 text-orange-300" };
    if (trigger === "NEWS_ALERT") return { label: isHe ? "חדשות" : "News Alert", color: "bg-purple-900/50 text-purple-300" };
    if (trigger === "EARNINGS") return { label: isHe ? "דוח רבעוני" : "Earnings", color: "bg-blue-900/50 text-blue-300" };
    return null;
  };

  const riskProfile = user?.risk_profile || "PASSIVE";
  const invType = (user as any)?.investment_type || "BOTH";

  const [perfSummary, setPerfSummary] = useState<any>(null);
  useEffect(() => {
    performanceApi.getSummary().then(setPerfSummary).catch(() => {});
  }, []);

  const stopLossWarnings = recommendations
    .filter(r => r.stop_loss && r.current_price_at_recommendation)
    .map(r => {
      const currentPrice = r.current_price_at_recommendation!;
      const stopLoss = r.stop_loss!;
      const pctFromStop = ((currentPrice - stopLoss) / stopLoss) * 100;
      return { symbol: r.symbol, currentPrice, stopLoss, pctFromStop };
    })
    .filter(w => w.pctFromStop >= 0 && w.pctFromStop <= 8);

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">
            {isHe ? `שלום, ${user?.full_name}` : `Hello, ${user?.full_name}`}
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            {new Date().toLocaleDateString(isHe ? "he-IL" : "en-US", {
              weekday: "long", year: "numeric", month: "long", day: "numeric",
            })}
          </p>
        </div>
        {unreadCount > 0 && (
          <Link
            to="/recommendations"
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-xl text-sm font-medium"
          >
            <span className="bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5">{unreadCount}</span>
            {isHe ? "הודעות חדשות" : "New Updates"}
          </Link>
        )}
      </div>

      {/* Profile Strip */}
      <div className="bg-gray-900 rounded-2xl px-5 py-4 border border-gray-800 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">{isHe ? "פרופיל:" : "Profile:"}</span>
          <span className={`font-bold text-sm ${riskColors[riskProfile] || "text-white"}`}>
            {riskLabels[riskProfile] ? (isHe ? riskLabels[riskProfile].he : riskLabels[riskProfile].en) : riskProfile}
          </span>
        </div>
        <div className="w-px h-4 bg-gray-700" />
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">{isHe ? "נכסים:" : "Assets:"}</span>
          <span className="text-sm font-medium text-white">
            {investmentTypeLabel[invType]?.icon} {isHe ? investmentTypeLabel[invType]?.he : investmentTypeLabel[invType]?.en}
          </span>
        </div>
        {(user as any)?.allows_volatile && (
          <span className="px-2 py-0.5 bg-red-900/40 text-red-300 rounded text-xs">{isHe ? "תנודתיות גבוהה" : "High Volatility"}</span>
        )}
        {(user as any)?.allows_leveraged && (
          <span className="px-2 py-0.5 bg-red-900/40 text-red-300 rounded text-xs">{isHe ? "ממונף" : "Leveraged"}</span>
        )}
        {(user as any)?.allows_short && (
          <span className="px-2 py-0.5 bg-red-900/40 text-red-300 rounded text-xs">Short</span>
        )}
        <div className="flex-1" />
        <Link to="/recommendations" className="text-xs text-blue-400 hover:text-blue-300">
          {isHe ? "עדכן פרופיל ←" : "Update profile →"}
        </Link>
      </div>

      {/* Portfolio Value Cards */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
            <p className="text-gray-400 text-xs mb-1">{isHe ? "שווי תיק כולל" : "Total Portfolio"}</p>
            <p className="text-2xl font-bold">{formatCurrency(summary.total_value)}</p>
            <p className={`text-sm mt-1 ${pnlPositive ? "text-green-400" : "text-red-400"}`}>
              {pnlPositive ? "+" : ""}{formatCurrency(summary.total_pnl)} ({summary.total_pnl_pct.toFixed(2)}%)
            </p>
          </div>
          <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
            <p className="text-gray-400 text-xs mb-1">{isHe ? "מזומן זמין" : "Available Cash"}</p>
            <p className="text-2xl font-bold text-green-400">{formatCurrency(summary.cash_balance)}</p>
          </div>
          <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
            <p className="text-gray-400 text-xs mb-1">{isHe ? "שווי שוק" : "Market Value"}</p>
            <p className="text-2xl font-bold">{formatCurrency(summary.total_market_value)}</p>
          </div>
          <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
            <p className="text-gray-400 text-xs mb-1">{isHe ? "ציון סיכון" : "Risk Score"}</p>
            <p className="text-2xl font-bold">
              <span className={riskColors[riskProfile] || "text-white"}>
                {summary.risk_score ?? user?.risk_score ?? "—"}/100
              </span>
            </p>
          </div>
        </div>
      )}

      {/* Stop-Loss Warnings */}
      {stopLossWarnings.length > 0 && (
        <div className="bg-red-900/20 border border-red-700/50 rounded-2xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-red-400 text-lg">⚠️</span>
            <h3 className="font-bold text-red-400">{isHe ? "אזהרת סטופ לוס" : "Stop-Loss Alert"}</h3>
          </div>
          {stopLossWarnings.map(w => (
            <div key={w.symbol} className="flex items-center justify-between text-sm py-1">
              <span className="font-bold">{w.symbol}</span>
              <span className="text-red-300">{isHe ? `מחיר נוכחי ₪${w.currentPrice} קרוב לסטופ ₪${w.stopLoss}` : `₪${w.currentPrice} near stop ₪${w.stopLoss}`}</span>
              <span className="text-red-400 font-bold">{w.pctFromStop.toFixed(1)}%</span>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Holdings */}
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold">{isHe ? "אחזקות עיקריות" : "Top Holdings"}</h2>
            <Link to="/portfolio" className="text-blue-400 text-sm hover:text-blue-300">
              {isHe ? "הכל" : "View all"}
            </Link>
          </div>
          {portfolioLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 bg-gray-800 rounded-xl animate-pulse" />
              ))}
            </div>
          ) : summary?.positions && summary.positions.length > 0 ? (
            <div className="space-y-3">
              {summary.positions.slice(0, 3).map((pos) => (
                <div key={pos.symbol} className="flex items-center justify-between p-3 bg-gray-800 rounded-xl">
                  <div>
                    <p className="font-bold">{pos.symbol}</p>
                    <p className="text-xs text-gray-400">{pos.quantity.toFixed(4)} {isHe ? "יח'" : "units"}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-medium">{formatCurrency(pos.current_value)}</p>
                    <p className={`text-xs ${pos.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {pos.pnl >= 0 ? "+" : ""}{pos.pnl_percentage.toFixed(2)}%
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500">
              <p>{isHe ? "אין אחזקות עדיין" : "No holdings yet"}</p>
              <Link to="/recommendations" className="text-blue-400 text-sm mt-2 block">
                {isHe ? "צפה בהמלצות לקנייה" : "View buy recommendations"}
              </Link>
            </div>
          )}
        </div>

        {/* Recent Notifications — trigger-aware */}
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold">{isHe ? "עדכונים אחרונים" : "Recent Updates"}</h2>
            <Link to="/recommendations" className="text-blue-400 text-sm hover:text-blue-300">
              {isHe ? "תיבת דואר" : "Inbox"}
            </Link>
          </div>
          {notifications.length > 0 ? (
            <div className="space-y-3">
              {notifications.slice(0, 4).map((notif) => {
                const badge = getTriggerBadge(notif);
                return (
                  <div
                    key={notif.id}
                    className={`p-3 rounded-xl border ${
                      !notif.is_read
                        ? "border-blue-700/50 bg-blue-900/10"
                        : "border-gray-800 bg-gray-800/50"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      {!notif.is_read && (
                        <span className="inline-block w-2 h-2 mt-1.5 bg-blue-400 rounded-full flex-shrink-0" />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-0.5">
                          {badge && (
                            <span className={`text-xs px-1.5 py-0.5 rounded ${badge.color}`}>
                              {badge.label}
                            </span>
                          )}
                          <p className="text-sm truncate">{notif.title || notif.external_message}</p>
                        </div>
                        <p className="text-xs text-gray-500">
                          {new Date(notif.sent_at).toLocaleString(isHe ? "he-IL" : "en-US")}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500">
              <p>{isHe ? "אין עדכונים חדשים" : "No recent updates"}</p>
            </div>
          )}
        </div>
      </div>

      {/* AI Performance Summary */}
      {perfSummary && perfSummary.total_tracked > 0 && (
        <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold text-sm">{isHe ? "ביצועי AI — מעקב המלצות" : "AI Performance Tracker"}</h2>
            <Link to="/fund" className="text-xs text-blue-400 hover:text-blue-300">
              {isHe ? "פרטים ←" : "Details →"}
            </Link>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: isHe ? "אחוז הצלחה" : "Win Rate", value: `${perfSummary.win_rate_pct}%`, color: "text-green-400" },
              { label: isHe ? "תשואה ממוצעת" : "Avg Return", value: `${perfSummary.avg_return_pct > 0 ? "+" : ""}${perfSummary.avg_return_pct}%`, color: perfSummary.avg_return_pct >= 0 ? "text-green-400" : "text-red-400" },
              { label: isHe ? "alpha vs S&P500" : "vs S&P 500", value: `${perfSummary.avg_vs_market_pct > 0 ? "+" : ""}${perfSummary.avg_vs_market_pct}%`, color: perfSummary.avg_vs_market_pct >= 0 ? "text-green-400" : "text-red-400" },
              { label: isHe ? "סה\"כ במעקב" : "Tracked", value: perfSummary.total_tracked, color: "text-white" },
            ].map(kpi => (
              <div key={kpi.label} className="bg-gray-800 rounded-xl p-3 text-center">
                <p className="text-xs text-gray-500 mb-1">{kpi.label}</p>
                <p className={`text-lg font-bold ${kpi.color}`}>{kpi.value}</p>
              </div>
            ))}
          </div>
          <div className="mt-3 flex gap-3">
            {/* Win bar */}
            <div className="flex-1">
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>{isHe ? "ניצחונות" : "Wins"} ({perfSummary.win_count})</span>
                <span>{isHe ? "הפסדים" : "Losses"} ({perfSummary.loss_count})</span>
              </div>
              <div className="w-full bg-red-900/40 rounded-full h-2 overflow-hidden">
                <div className="bg-green-500 h-2 rounded-full" style={{ width: `${perfSummary.win_rate_pct}%` }} />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { to: "/recommendations", icon: "💡", he: "המלצות AI", en: "AI Recommendations" },
          { to: "/portfolio", icon: "📊", he: "תיק השקעות", en: "Portfolio" },
          { to: "/watchlist", icon: "👁", he: "רשימת מעקב", en: "Watchlist" },
          { to: "/orders", icon: "📋", he: "היסטוריית עסקאות", en: "Trade History" },
        ].map((action) => (
          <Link
            key={action.to}
            to={action.to}
            className="bg-gray-900 hover:bg-gray-800 border border-gray-800 rounded-2xl p-4 flex items-center gap-3 transition-colors"
          >
            <span className="text-2xl">{action.icon}</span>
            <span className="text-sm font-medium">{isHe ? action.he : action.en}</span>
          </Link>
        ))}
      </div>
    </div>
  );
};

export default Dashboard;
