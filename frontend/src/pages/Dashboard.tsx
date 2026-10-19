import React, { useEffect, useState } from "react";
import { useT } from "../i18n/t";
import { Link } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../store";
import { fetchInbox, fetchUnreadCount, fetchRecommendations } from "../store/slices/notificationsSlice";
import { performanceApi, watchlistApi } from "../api/client";
import { WatchlistItem, Recommendation } from "../types";

const Dashboard: React.FC = () => {
  const t = useT();
  const dispatch = useAppDispatch();
  const { user } = useAppSelector((state) => state.auth);
  const { notifications, unreadCount, recommendations } = useAppSelector((state) => state.notifications);

  const isHe = user?.preferred_language === "he";

  useEffect(() => {
    dispatch(fetchInbox({ unreadOnly: false }));
    dispatch(fetchRecommendations({}));
  }, [dispatch]);

  const getTriggerBadge = (notif: any) => {
    const trigger = notif.internal_detail?.trigger_type;
    if (trigger === "PRICE_ALERT") return { label: t("Price Alert", "תנועת מחיר"), color: "bg-orange-900/50 text-orange-300" };
    if (trigger === "NEWS_ALERT") return { label: t("News Alert", "חדשות"), color: "bg-purple-900/50 text-purple-300" };
    if (trigger === "EARNINGS") return { label: t("Earnings", "דוח רבעוני"), color: "bg-blue-900/50 text-blue-300" };
    return null;
  };

  const [perfSummary, setPerfSummary] = useState<any>(null);
  useEffect(() => {
    performanceApi.getSummary().then(setPerfSummary).catch(() => {});
  }, []);

  // The overview is built around what the reader follows. It used to be
  // built around a portfolio — value, cash, holdings — and with nothing in
  // the app that records a trade, every new account saw zeros and "no
  // holdings yet" on its first screen.
  const [watch, setWatch] = useState<WatchlistItem[] | null>(null);
  useEffect(() => {
    watchlistApi.getWatchlist().then(setWatch).catch(() => setWatch([]));
  }, []);

  const recBySymbol = new Map<string, Recommendation>();
  for (const r of recommendations) if (!recBySymbol.has(r.symbol)) recBySymbol.set(r.symbol, r);

  const signalOf = (w: WatchlistItem) =>
    String(w.technical_signal || w.last_technical_analysis?.timing_signal || "").toUpperCase();

  // Same rule as the "Enter now" filter in Signals: a BUY at 60%+ whose
  // technical is BUY, stop intact, target not yet reached.
  const isEntry = (w: WatchlistItem) => {
    const r = recBySymbol.get(w.symbol);
    if (!r || !r.recommendation_type.includes("BUY") || r.confidence_score < 60 || r.level_hit) return false;
    const sig = signalOf(w);
    if (sig !== "BUY_NOW" && sig !== "STRONG_BUY") return false;
    const px = typeof r.current_price === "number" ? r.current_price : w.current_price;
    return !(px && r.target_price && px >= r.target_price);
  };

  // Near the stop on today's price — not the price at recommendation, which
  // is what the old warning measured and could be weeks out of date.
  const stopStatus = (w: WatchlistItem): { kind: "broken" | "near"; pct: number; stop: number } | null => {
    const r = recBySymbol.get(w.symbol);
    const px = typeof r?.current_price === "number" ? r.current_price : w.current_price;
    if (!r?.stop_loss || !px) return null;
    const short = r.recommendation_type.includes("SELL");
    const pct = short ? ((r.stop_loss - px) / px) * 100 : ((px - r.stop_loss) / px) * 100;
    if (r.level_hit === "STOP" || pct < 0) return { kind: "broken", pct, stop: r.stop_loss };
    if (pct <= 3) return { kind: "near", pct, stop: r.stop_loss };
    return null;
  };

  const watched = watch ?? [];
  const entryCount = watched.filter(isEntry).length;
  const stopRows = watched.map((w) => ({ w, st: stopStatus(w) })).filter((x) => x.st);

  // Direct t() calls: the string scanner only sees literals passed to t().
  const sigStyle = (sig: string) =>
    sig.includes("BUY") ? { cls: "text-green-400", label: t("Buy", "קנה") }
    : sig.includes("SELL") ? { cls: "text-red-400", label: t("Sell", "מכור") }
    : { cls: "text-yellow-400", label: t("Wait", "המתן") };

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">
            {t("Hello, {name}", "שלום, {name}", { name: user?.full_name ?? "" })}
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
            {t("New Updates", "הודעות חדשות")}
          </Link>
        )}
      </div>

      {/* At a glance */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { to: "/watchlist", value: watch === null ? "…" : watched.length, label: t("Following", "במעקב"), cls: "text-white" },
          { to: "/recommendations", value: watch === null ? "…" : entryCount, label: t("At an entry point", "בנקודת כניסה"), cls: entryCount > 0 ? "text-green-400" : "text-white" },
          { to: "/recommendations", value: unreadCount ?? 0, label: t("New alerts", "התראות חדשות"), cls: (unreadCount ?? 0) > 0 ? "text-blue-400" : "text-white" },
        ].map((c) => (
          <Link key={c.label} to={c.to} className="bg-gray-900 hover:bg-gray-800 rounded-2xl p-4 border border-gray-800 text-center transition-colors">
            <p className={`text-2xl font-bold num ${c.cls}`}>{c.value}</p>
            <p className="text-xs text-gray-400 mt-1">{c.label}</p>
          </Link>
        ))}
      </div>

      {/* Stop warnings on followed stocks */}
      {stopRows.length > 0 && (
        <div className="bg-red-900/20 border border-red-700/50 rounded-2xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-red-400 text-lg">⚠️</span>
            <h3 className="font-bold text-red-400">{t("Stop loss", "סטופ לוס")}</h3>
          </div>
          {stopRows.map(({ w, st }) => (
            <div key={w.symbol} className="flex items-center justify-between text-sm py-1 gap-3">
              <span className="font-bold">{w.symbol}</span>
              <span className={st!.kind === "broken" ? "text-red-300" : "text-orange-300"}>
                {st!.kind === "broken"
                  ? t("Stop {stop} broken", "הסטופ {stop} נשבר", { stop: `$${st!.stop.toFixed(2)}` })
                  : t("{pct}% above the stop {stop}", "{pct}% מעל הסטופ {stop}", { pct: st!.pct.toFixed(1), stop: `$${st!.stop.toFixed(2)}` })}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Followed stocks */}
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold">{t("Stocks you follow", "המניות שאתה עוקב אחריהן")}</h2>
            <Link to="/watchlist" className="text-blue-400 text-sm hover:text-blue-300">
              {t("View all", "הכל")}
            </Link>
          </div>
          {watch === null ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-14 bg-gray-800 rounded-xl animate-pulse" />
              ))}
            </div>
          ) : watched.length > 0 ? (
            <div className="space-y-2">
              {watched.slice(0, 6).map((w) => {
                const sig = sigStyle(signalOf(w));
                const entry = isEntry(w);
                return (
                  <Link key={w.id} to="/watchlist" className="flex items-center justify-between p-3 bg-gray-800 rounded-xl hover:bg-gray-700/70">
                    <div className="min-w-0">
                      <p className="font-bold">{w.symbol}</p>
                      {w.asset_name && <p className="text-xs text-gray-400 truncate">{w.asset_name}</p>}
                    </div>
                    <div className="text-end shrink-0">
                      <p className={`text-sm font-bold ${entry ? "text-green-400" : sig.cls}`}>
                        {entry ? `🟢 ${t("Enter now", "כניסה עכשיו")}` : sig.label}
                      </p>
                      {typeof w.current_price === "number" && (
                        <p className="text-xs text-gray-400 num" dir="ltr">${w.current_price.toFixed(2)}</p>
                      )}
                    </div>
                  </Link>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500">
              <p>{t("You are not following any stock yet", "עדיין אינך עוקב אחרי אף מניה")}</p>
              <Link to="/recommendations" className="text-blue-400 text-sm mt-2 block">
                {t("Browse signals and tap Follow", "עבור לסיגנלים ולחץ \"עקוב\"")}
              </Link>
            </div>
          )}
        </div>

        {/* Recent Notifications — trigger-aware */}
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold">{t("Recent Updates", "עדכונים אחרונים")}</h2>
            <Link to="/recommendations" className="text-blue-400 text-sm hover:text-blue-300">
              {t("Inbox", "תיבת דואר")}
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
              <p>{t("No recent updates", "אין עדכונים חדשים")}</p>
            </div>
          )}
        </div>
      </div>

      {/* AI Performance Summary */}
      {perfSummary && perfSummary.total_tracked > 0 && (
        <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold text-sm">{t("AI Performance Tracker", "ביצועי AI — מעקב המלצות")}</h2>
            <Link to="/fund" className="text-xs text-blue-400 hover:text-blue-300">
              {t("Details →", "פרטים ←")}
            </Link>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: t("Win Rate", "אחוז הצלחה"), value: `${perfSummary.win_rate_pct}%`, color: "text-green-400" },
              { label: t("Avg Return", "תשואה ממוצעת"), value: `${perfSummary.avg_return_pct > 0 ? "+" : ""}${perfSummary.avg_return_pct}%`, color: perfSummary.avg_return_pct >= 0 ? "text-green-400" : "text-red-400" },
              { label: isHe ? "alpha vs S&P500" : "vs S&P 500", value: `${perfSummary.avg_vs_market_pct > 0 ? "+" : ""}${perfSummary.avg_vs_market_pct}%`, color: perfSummary.avg_vs_market_pct >= 0 ? "text-green-400" : "text-red-400" },
              { label: t("Tracked", "סה\"כ במעקב"), value: perfSummary.total_tracked, color: "text-white" },
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
                <span>{t("Wins", "ניצחונות")} ({perfSummary.win_count})</span>
                <span>{t("Losses", "הפסדים")} ({perfSummary.loss_count})</span>
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
          { to: "/watchlist", icon: "👁", he: "רשימת מעקב", en: "Watchlist" },
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
