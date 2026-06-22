import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAppSelector } from "../store";
import { marketApi } from "../api/client";
import { RecommendationType } from "../types";

interface MasterListEntry {
  id: number;
  symbol: string;
  asset_name?: string;
  recommendation_type: string;
  confidence_score: number;
  target_price?: number;
  stop_loss?: number;
  current_price?: number;
  expected_return_pct?: number;
  thesis?: string;
  sector?: string;
  quarter: string;
  published_at: string;
  recommendation_id?: number;
}

interface MasterListResponse {
  quarter: string | null;
  entries: MasterListEntry[];
}

const recBadgeClass = (type: string) => {
  if (type === "STRONG_BUY") return "bg-green-500/20 text-green-300 border border-green-600/40";
  if (type === "BUY") return "bg-green-900/30 text-green-400 border border-green-700/40";
  if (type === "STRONG_SELL") return "bg-red-500/20 text-red-300 border border-red-600/40";
  if (type === "SELL") return "bg-red-900/30 text-red-400 border border-red-700/40";
  return "bg-gray-800 text-gray-400 border border-gray-700";
};

const isLong = (type: string) => type === "BUY" || type === "STRONG_BUY";

const MasterList: React.FC = () => {
  const { user } = useAppSelector((s) => s.auth);
  const isHe = user?.preferred_language === "he";

  const [data, setData] = useState<MasterListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPublishing, setIsPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<string | null>(null);
  const [dirFilter, setDirFilter] = useState<"ALL" | "LONG" | "SHORT">("ALL");

  const load = async () => {
    setIsLoading(true);
    try {
      const res = await marketApi.getMasterList();
      setData(res);
    } catch {
      setData({ quarter: null, entries: [] });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handlePublish = async () => {
    setIsPublishing(true);
    setPublishResult(null);
    try {
      const res = await marketApi.publishMasterList();
      setPublishResult(
        isHe
          ? `פורסם! ${res.buys} קניות + ${res.sells} מכירות לרבעון ${res.quarter}`
          : `Published! ${res.buys} buys + ${res.sells} sells for ${res.quarter}`
      );
      await load();
    } catch (e: any) {
      setPublishResult(
        isHe ? "שגיאה בפרסום" : "Failed to publish"
      );
    } finally {
      setIsPublishing(false);
    }
  };

  const entries = data?.entries ?? [];
  const longs = entries.filter((e) => isLong(e.recommendation_type));
  const shorts = entries.filter((e) => !isLong(e.recommendation_type));
  const filtered = dirFilter === "LONG" ? longs : dirFilter === "SHORT" ? shorts : entries;

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">
            {isHe ? "רשימת המאסטר — המלצות רבעוניות" : "Master List — Quarterly Picks"}
          </h1>
          {data?.quarter && (
            <p className="text-sm text-gray-400 mt-0.5">
              {isHe ? `רבעון פעיל: ${data.quarter}` : `Active quarter: ${data.quarter}`}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handlePublish}
            disabled={isPublishing}
            className="text-sm bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded-xl transition-colors"
          >
            {isPublishing
              ? (isHe ? "מפרסם..." : "Publishing...")
              : (isHe ? "פרסם רשימה חדשה" : "Publish New List")}
          </button>
          <Link to="/recommendations" className="text-xs text-gray-400 hover:text-gray-200">
            {isHe ? "← סיגנלים" : "Signals →"}
          </Link>
        </div>
      </div>

      {publishResult && (
        <div className="bg-blue-900/30 border border-blue-700/40 rounded-xl px-4 py-3 text-sm text-blue-300">
          {publishResult}
        </div>
      )}

      {/* Stats */}
      {!isLoading && entries.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-gray-900 rounded-xl p-4 border border-gray-800 text-center">
            <p className="text-2xl font-bold text-white">{entries.length}</p>
            <p className="text-xs text-gray-400 mt-0.5">{isHe ? "סה\"כ מניות" : "Total Stocks"}</p>
          </div>
          <div className="bg-gray-900 rounded-xl p-4 border border-green-900/30 text-center">
            <p className="text-2xl font-bold text-green-400">{longs.length}</p>
            <p className="text-xs text-gray-400 mt-0.5">LONG</p>
          </div>
          <div className="bg-gray-900 rounded-xl p-4 border border-red-900/30 text-center">
            <p className="text-2xl font-bold text-red-400">{shorts.length}</p>
            <p className="text-xs text-gray-400 mt-0.5">SHORT</p>
          </div>
        </div>
      )}

      {/* Filter */}
      {!isLoading && entries.length > 0 && (
        <div className="flex items-center gap-2">
          {(["ALL", "LONG", "SHORT"] as const).map((f) => (
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
              {f === "LONG" ? `LONG (${longs.length})` : f === "SHORT" ? `SHORT (${shorts.length})` : `${isHe ? "הכל" : "All"} (${entries.length})`}
            </button>
          ))}
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-24 bg-gray-900 rounded-2xl animate-pulse" />
          ))}
        </div>
      )}

      {/* Empty */}
      {!isLoading && entries.length === 0 && (
        <div className="bg-gray-900 rounded-2xl p-16 border border-gray-800 text-center text-gray-500">
          <p className="text-4xl mb-3">📋</p>
          <p className="text-lg font-medium mb-1">
            {isHe ? "אין רשימת מאסטר פעילה" : "No active master list"}
          </p>
          <p className="text-sm">
            {isHe
              ? "לחץ על \"פרסם רשימה חדשה\" כדי ליצור את רשימת המאסטר הרבעונית מהמלצות מאושרות"
              : "Click \"Publish New List\" to create the quarterly master list from approved recommendations"}
          </p>
        </div>
      )}

      {/* Entries */}
      {!isLoading && filtered.length > 0 && (
        <div className="space-y-3">
          {filtered.map((entry, idx) => {
            const long = isLong(entry.recommendation_type);
            return (
              <div
                key={entry.id}
                className={`bg-gray-900 rounded-2xl p-5 border transition-colors hover:border-gray-600 ${
                  long ? "border-green-900/40" : "border-red-900/40"
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    {/* Rank + Symbol + Badge */}
                    <div className="flex items-center gap-2 flex-wrap mb-2">
                      <span className="text-xs text-gray-600 font-mono w-5">#{idx + 1}</span>
                      <span className="font-mono font-bold text-lg">{entry.symbol}</span>
                      <span className={`text-xs px-2 py-0.5 rounded border ${recBadgeClass(entry.recommendation_type)}`}>
                        {entry.recommendation_type.replace("_", " ")}
                      </span>
                      {entry.sector && (
                        <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
                          {entry.sector}
                        </span>
                      )}
                    </div>

                    {/* Asset name or thesis */}
                    {entry.thesis ? (
                      <p className="text-sm text-gray-300 line-clamp-2">{entry.thesis}</p>
                    ) : entry.asset_name ? (
                      <p className="text-sm text-gray-400">{entry.asset_name}</p>
                    ) : null}

                    {/* Key metrics */}
                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-400 flex-wrap">
                      <span>
                        {isHe ? "ביטחון:" : "Conf:"}{" "}
                        <span className="text-white font-medium">{entry.confidence_score.toFixed(0)}%</span>
                      </span>
                      {entry.current_price && (
                        <span>
                          {isHe ? "מחיר:" : "Price:"}{" "}
                          <span className="text-white font-medium">${entry.current_price.toFixed(2)}</span>
                        </span>
                      )}
                      {entry.target_price && (
                        <span>
                          {isHe ? "יעד:" : "Target:"}{" "}
                          <span className={long ? "text-green-400" : "text-red-400"} style={{ fontWeight: 500 }}>
                            ${entry.target_price.toFixed(2)}
                          </span>
                        </span>
                      )}
                      {entry.stop_loss && (
                        <span>Stop: <span className="text-white font-medium">${entry.stop_loss.toFixed(2)}</span></span>
                      )}
                      {entry.expected_return_pct != null && (
                        <span className={entry.expected_return_pct >= 0 ? "text-green-400" : "text-red-400"}>
                          {entry.expected_return_pct >= 0 ? "+" : ""}{entry.expected_return_pct.toFixed(1)}%
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  {entry.recommendation_id && (
                    <Link
                      to={`/research/${entry.recommendation_id}`}
                      className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded-lg flex-shrink-0"
                    >
                      {isHe ? "דוח מחקר" : "Research"}
                    </Link>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default MasterList;
