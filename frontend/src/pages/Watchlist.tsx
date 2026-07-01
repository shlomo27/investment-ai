import React, { useEffect, useState } from "react";
import { useAppSelector } from "../store";
import { watchlistApi, marketApi } from "../api/client";
import { WatchlistItem, TechnicalAnalysis } from "../types";
import PriceChart from "../components/Charts/PriceChart";

const Watchlist: React.FC = () => {
  const { user } = useAppSelector((state) => state.auth);
  const isHe = user?.preferred_language === "he";

  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [technicalLoading, setTechnicalLoading] = useState<number | null>(null);
  const [expandedItem, setExpandedItem] = useState<number | null>(null);
  const [alertEditing, setAlertEditing] = useState<number | null>(null);
  const [alertAbove, setAlertAbove] = useState<string>("");
  const [alertBelow, setAlertBelow] = useState<string>("");
  const [alertSaving, setAlertSaving] = useState(false);

  useEffect(() => {
    fetchWatchlist();
  }, []);

  const fetchWatchlist = async () => {
    setIsLoading(true);
    try {
      const data = await watchlistApi.getWatchlist();
      setItems(data);
    } catch (e) {
      console.error(e);
    }
    setIsLoading(false);
  };

  const handleSearch = async (q: string) => {
    setSearchQuery(q);
    if (q.length < 2) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    try {
      const [global, tase] = await Promise.all([
        marketApi.search(q),
        marketApi.searchTASE(q),
      ]);
      setSearchResults([...global, ...tase].slice(0, 10));
    } catch (e) {
      console.error(e);
    }
    setSearchLoading(false);
  };

  const handleAdd = async (symbol: string, exchange: string) => {
    try {
      await watchlistApi.addToWatchlist({ symbol, exchange });
      setSearchQuery("");
      setSearchResults([]);
      fetchWatchlist();
    } catch (e: any) {
      alert(e.response?.data?.detail || "Failed to add");
    }
  };

  const handleRemove = async (id: number) => {
    if (!window.confirm(isHe ? "להסיר מרשימת המעקב?" : "Remove from watchlist?")) return;
    try {
      await watchlistApi.removeFromWatchlist(id);
      setItems(items.filter((i) => i.id !== id));
    } catch (e: any) {
      alert(e.response?.data?.detail || "Failed to remove");
    }
  };

  const handleRunTechnical = async (id: number) => {
    setTechnicalLoading(id);
    try {
      const result = await watchlistApi.runTechnicalAnalysis(id);
      setItems(items.map((item) =>
        item.id === id
          ? { ...item, last_technical_analysis: result.technical_analysis, technical_signal: result.technical_analysis?.timing_signal as any }
          : item
      ));
      setExpandedItem(id);
    } catch (e: any) {
      alert(e.response?.data?.detail || "Analysis failed");
    }
    setTechnicalLoading(null);
  };

  const handleSaveAlert = async (itemId: number) => {
    setAlertSaving(true);
    try {
      await watchlistApi.setPriceAlert(
        itemId,
        alertAbove ? parseFloat(alertAbove) : undefined,
        alertBelow ? parseFloat(alertBelow) : undefined,
      );
      setAlertEditing(null);
      fetchWatchlist();
    } catch (e: any) {
      alert(e.response?.data?.detail || "Failed to save alert");
    }
    setAlertSaving(false);
  };

  const signalColor = (signal?: string) => {
    if (!signal || signal === "WAIT") return "text-yellow-400";
    if (signal.includes("BUY")) return "text-green-400";
    if (signal.includes("SELL")) return "text-red-400";
    return "text-gray-400";
  };

  const signalLabel = (signal?: string) => {
    const labels: Record<string, string> = {
      STRONG_BUY: "🟢 STRONG BUY",
      BUY_NOW: "🟢 BUY",
      WAIT: "🟡 WAIT",
      SELL_NOW: "🔴 SELL",
      STRONG_SELL: "🔴 STRONG SELL",
    };
    return labels[signal || ""] || signal || "—";
  };

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="space-y-6">
      <h1 className="text-2xl font-bold">{isHe ? "רשימת מעקב" : "Watchlist"}</h1>

      {/* Search & Add */}
      <div className="relative">
        <div className="flex gap-3">
          <div className="relative flex-1">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => handleSearch(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-blue-500"
              placeholder={isHe ? "חפש מניה (AAPL, MSFT, תשלב...)" : "Search stock (AAPL, MSFT, TASE...)"}
            />
            {searchLoading && (
              <div className="absolute right-3 top-3">
                <div className="animate-spin h-5 w-5 border-2 border-blue-500 border-t-transparent rounded-full" />
              </div>
            )}
          </div>
        </div>

        {searchResults.length > 0 && (
          <div className="absolute top-14 left-0 right-0 bg-gray-800 border border-gray-700 rounded-xl overflow-hidden z-10 shadow-xl">
            {searchResults.map((result, i) => (
              <div
                key={i}
                className="flex items-center justify-between px-4 py-3 hover:bg-gray-700 cursor-pointer border-b border-gray-700 last:border-0"
                onClick={() => handleAdd(result.symbol, result.exchange || "NASDAQ")}
              >
                <div>
                  <span className="font-bold">{result.symbol}</span>
                  <span className="text-gray-400 text-sm ml-2">{result.name}</span>
                </div>
                <span className="text-xs text-gray-500 bg-gray-900 px-2 py-1 rounded">{result.exchange}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Watchlist Items */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 bg-gray-900 rounded-2xl animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="bg-gray-900 rounded-2xl p-12 border border-gray-800 text-center text-gray-500">
          <p className="text-4xl mb-3">👁</p>
          <p>{isHe ? "רשימת המעקב ריקה" : "Watchlist is empty"}</p>
          <p className="text-sm mt-1">{isHe ? "חפש מניות להוסיף" : "Search stocks to add"}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => {
            const tech = item.last_technical_analysis;
            const isExpanded = expandedItem === item.id;

            return (
              <div key={item.id} className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">
                <div className="p-5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-lg">{item.symbol}</span>
                          {item.asset_name && (
                            <span className="text-gray-400 text-sm">{item.asset_name}</span>
                          )}
                        </div>
                        {item.current_price && (
                          <span className="text-sm text-gray-400">
                            ₪{item.current_price.toLocaleString("en", { minimumFractionDigits: 2 })}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      {tech?.timing_signal && (
                        <span className={`text-sm font-bold ${signalColor(tech.timing_signal)}`}>
                          {signalLabel(tech.timing_signal)}
                        </span>
                      )}
                      <button
                        onClick={() => {
                          setAlertEditing(alertEditing === item.id ? null : item.id);
                          setAlertAbove(item.alert_price_above ? String(item.alert_price_above) : "");
                          setAlertBelow(item.alert_price_below ? String(item.alert_price_below) : "");
                        }}
                        className="text-xs bg-yellow-600/20 border border-yellow-600/50 text-yellow-400 px-3 py-1.5 rounded-lg hover:bg-yellow-600/30"
                        title={isHe ? "הגדר התראת מחיר" : "Set price alert"}
                      >
                        🔔
                      </button>
                      <button
                        onClick={() => handleRunTechnical(item.id)}
                        disabled={technicalLoading === item.id}
                        className="text-xs bg-blue-600/20 border border-blue-600/50 text-blue-400 px-3 py-1.5 rounded-lg hover:bg-blue-600/30 disabled:opacity-50"
                      >
                        {technicalLoading === item.id
                          ? (isHe ? "מנתח..." : "Analyzing...")
                          : (isHe ? "ניתוח טכני" : "Technical")}
                      </button>
                      <button
                        onClick={() => tech && setExpandedItem(isExpanded ? null : item.id)}
                        className={`text-gray-400 hover:text-white ${!tech && "opacity-30 cursor-not-allowed"}`}
                        disabled={!tech}
                      >
                        {isExpanded ? "▲" : "▼"}
                      </button>
                      <button
                        onClick={() => handleRemove(item.id)}
                        className="text-red-500 hover:text-red-400 text-sm"
                      >
                        ×
                      </button>
                    </div>
                  </div>
                </div>

                {/* Price Alert Panel */}
                {alertEditing === item.id && (
                  <div className="border-t border-gray-800 p-4 bg-yellow-900/10">
                    <p className="text-xs font-medium text-yellow-400 mb-3">
                      🔔 {isHe ? "התראת מחיר" : "Price Alert"}
                    </p>
                    <div className="flex gap-3 items-end flex-wrap">
                      <div>
                        <label className="text-xs text-gray-400 block mb-1">{isHe ? "התראה מעל" : "Alert above"}</label>
                        <input
                          type="number"
                          value={alertAbove}
                          onChange={e => setAlertAbove(e.target.value)}
                          placeholder="e.g. 200"
                          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white w-28"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-400 block mb-1">{isHe ? "התראה מתחת" : "Alert below"}</label>
                        <input
                          type="number"
                          value={alertBelow}
                          onChange={e => setAlertBelow(e.target.value)}
                          placeholder="e.g. 150"
                          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white w-28"
                        />
                      </div>
                      <button
                        onClick={() => handleSaveAlert(item.id)}
                        disabled={alertSaving}
                        className="text-xs bg-yellow-600 hover:bg-yellow-500 disabled:bg-gray-700 text-white px-3 py-1.5 rounded-lg"
                      >
                        {alertSaving ? (isHe ? "שומר..." : "Saving...") : (isHe ? "שמור" : "Save")}
                      </button>
                      <button
                        onClick={() => setAlertEditing(null)}
                        className="text-xs text-gray-400 hover:text-gray-200 px-2 py-1.5"
                      >
                        {isHe ? "ביטול" : "Cancel"}
                      </button>
                    </div>
                    {(item.alert_price_above || item.alert_price_below) && (
                      <p className="text-xs text-gray-500 mt-2">
                        {isHe ? "התראות פעילות: " : "Active alerts: "}
                        {item.alert_price_above ? `▲$${item.alert_price_above}` : ""}
                        {item.alert_price_above && item.alert_price_below ? " / " : ""}
                        {item.alert_price_below ? `▼$${item.alert_price_below}` : ""}
                      </p>
                    )}
                  </div>
                )}

                {/* Technical Details */}
                {isExpanded && tech && (
                  <div className="border-t border-gray-800 p-5 bg-gray-800/30">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                      {[
                        { label: "RSI (14)", value: tech.rsi_14?.toFixed(1) || "N/A", signal: tech.rsi_signal },
                        { label: "MACD", value: tech.macd?.toFixed(2) || "N/A", signal: tech.macd_crossover },
                        { label: "MA 50", value: tech.ma_50 ? `₪${tech.ma_50.toFixed(2)}` : "N/A" },
                        { label: "MA 200", value: tech.ma_200 ? `₪${tech.ma_200.toFixed(2)}` : "N/A" },
                      ].map((ind) => (
                        <div key={ind.label} className="bg-gray-900 rounded-xl p-3">
                          <p className="text-xs text-gray-500 mb-1">{ind.label}</p>
                          <p className="font-bold">{ind.value}</p>
                          {ind.signal && <p className="text-xs text-gray-400">{ind.signal}</p>}
                        </div>
                      ))}
                    </div>

                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-400">{isHe ? "ציון טכני" : "Technical Score"}</span>
                        <span className="font-bold">{tech.technical_score}/100</span>
                      </div>
                      {tech.signal_reasoning && (
                        <p className="text-xs text-gray-400 mt-2">{tech.signal_reasoning}</p>
                      )}
                      {tech.support_levels?.length > 0 && (
                        <div className="text-xs text-gray-400">
                          <span>{isHe ? "תמיכה: " : "Support: "}</span>
                          {tech.support_levels.map((s) => `₪${s.toFixed(2)}`).join(", ")}
                        </div>
                      )}
                      {tech.resistance_levels?.length > 0 && (
                        <div className="text-xs text-gray-400">
                          <span>{isHe ? "התנגדות: " : "Resistance: "}</span>
                          {tech.resistance_levels.map((r) => `₪${r.toFixed(2)}`).join(", ")}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default Watchlist;
