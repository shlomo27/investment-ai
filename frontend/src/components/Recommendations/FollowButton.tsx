import React, { useState } from "react";
import { useT } from "../../i18n/t";
import { watchlistApi } from "../../api/client";

/**
 * The one action offered on a stock: follow it.
 *
 * The app does not buy, sell or record trades. A "buy" or "add to portfolio"
 * button next to an analysis reads as an instruction to transact — which is
 * investment advice, and a service the app is not licensed to provide.
 * Following puts the stock on the watchlist, and from then on its trend
 * changes, stop and target reach the reader as alerts.
 */
const FollowButton: React.FC<{ symbol: string; size?: "sm" | "lg" }> = ({ symbol, size = "sm" }) => {
  const t = useT();
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");

  const follow = async () => {
    setState("busy");
    try {
      await watchlistApi.addToWatchlist({
        symbol,
        exchange: symbol.endsWith(".TA") ? "TASE" : "NASDAQ",
        alert_on_technical_signal: true,
        notes: "Followed from analysis",
      });
    } catch {
      // Already on the watchlist is the common failure, and is success here.
    }
    setState("done");
  };

  if (state === "done") {
    return (
      <span className={`text-green-400 px-2 ${size === "lg" ? "text-sm" : "text-xs"}`}>
        {t("✓ Following — we'll alert you", "✓ במעקב — נעדכן אותך בהתראות")}
      </span>
    );
  }
  return (
    <button
      onClick={follow}
      disabled={state === "busy"}
      title={t("Get alerts on this stock's trend changes, stop and target", "קבל התראות על שינויי מגמה, סטופ ויעד במניה הזו")}
      className={
        size === "lg"
          ? "w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white rounded-xl py-3 font-medium"
          : "bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white rounded-lg px-4 py-1.5 text-sm font-medium"
      }
    >
      {state === "busy" ? "..." : `👁 ${t("Follow", "עקוב")}`}
    </button>
  );
};

export default FollowButton;
