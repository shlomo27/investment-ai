import React, { useEffect } from "react";
import { Link } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../store";
import { fetchPortfolioSummary } from "../store/slices/portfolioSlice";
import { fetchInbox, fetchUnreadCount } from "../store/slices/notificationsSlice";
import PriceChart from "../components/Charts/PriceChart";

const Dashboard: React.FC = () => {
  const dispatch = useAppDispatch();
  const { user } = useAppSelector((state) => state.auth);
  const { summary, isLoading: portfolioLoading } = useAppSelector((state) => state.portfolio);
  const { notifications, unreadCount } = useAppSelector((state) => state.notifications);

  const isHe = user?.preferred_language === "he";

  useEffect(() => {
    dispatch(fetchPortfolioSummary());
    dispatch(fetchInbox({ unreadOnly: false }));
  }, [dispatch]);

  const formatCurrency = (value: number, currency = "₪") =>
    `${currency}${Math.abs(value).toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const pnlPositive = (summary?.total_pnl || 0) >= 0;

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
              weekday: "long", year: "numeric", month: "long", day: "numeric"
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
            <p className="text-gray-400 text-xs mb-1">{isHe ? "רמת סיכון" : "Risk Level"}</p>
            <p className="text-2xl font-bold">
              <span className={
                summary.risk_level === "HIGH" ? "text-red-400" :
                summary.risk_level === "MEDIUM" ? "text-yellow-400" : "text-green-400"
              }>
                {summary.risk_level || "N/A"}
              </span>
            </p>
            <p className="text-xs text-gray-500">{isHe ? `ציון: ${summary.risk_score || "N/A"}/100` : `Score: ${summary.risk_score || "N/A"}/100`}</p>
          </div>
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

        {/* Recent Notifications */}
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold">{isHe ? "עדכונים אחרונים" : "Recent Updates"}</h2>
            <Link to="/recommendations" className="text-blue-400 text-sm hover:text-blue-300">
              {isHe ? "תיבת דואר" : "Inbox"}
            </Link>
          </div>
          {notifications.length > 0 ? (
            <div className="space-y-3">
              {notifications.slice(0, 4).map((notif) => (
                <div
                  key={notif.id}
                  className={`p-3 rounded-xl border ${
                    !notif.is_read
                      ? "border-blue-700/50 bg-blue-900/10"
                      : "border-gray-800 bg-gray-800/50"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm">
                      {!notif.is_read && (
                        <span className="inline-block w-2 h-2 bg-blue-400 rounded-full mr-1.5 mb-0.5" />
                      )}
                      {notif.title || notif.external_message}
                    </p>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    {new Date(notif.sent_at).toLocaleString(isHe ? "he-IL" : "en-US")}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500">
              <p>{isHe ? "אין עדכונים חדשים" : "No recent updates"}</p>
            </div>
          )}
        </div>
      </div>

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
