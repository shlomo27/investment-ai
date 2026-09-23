import React, { useState } from "react";
import { useT } from "../../i18n/t";
import { useNavigate } from "react-router-dom";
import { watchlistApi } from "../../api/client";
import { Recommendation, RecommendationType, OrderType, TechnicalAnalysis } from "../../types";

interface Props {
  recommendation: Recommendation;
  isHe: boolean;
  technicalAnalysis?: TechnicalAnalysis;
  isLoadingTechnical: boolean;
  onRequestTechnical: () => void;
  onBuy: () => void;
  onSell: () => void;
  onDismiss: () => void;
  suggestedAmount?: number; // legacy — no longer rendered
  suggestedPct?: number;
  approvedAt?: string;
}

const RecommendationCard: React.FC<Props> = ({
  recommendation: rec,
  isHe,
  technicalAnalysis: tech,
  isLoadingTechnical,
  onRequestTechnical,
  onBuy,
  onSell,
  onDismiss,
  suggestedAmount,
  suggestedPct,
  approvedAt,
}) => {
  const t = useT();
  const [expanded, setExpanded] = useState(false);
  const [following, setFollowing] = useState(false);
  const [followMsg, setFollowMsg] = useState(false);
  const navigate = useNavigate();

  const handleFollowForEntry = async () => {
    setFollowing(true);
    try {
      await watchlistApi.addToWatchlist({
        symbol: rec.symbol,
        exchange: rec.symbol.endsWith(".TA") ? "TASE" : "NASDAQ",
        alert_on_technical_signal: true,
        notes: "Following for entry point",
      });
      setFollowMsg(true);
    } catch {
      // already on watchlist or failed — still show confirmation
      setFollowMsg(true);
    }
    setFollowing(false);
  };

  const isBuy = rec.recommendation_type.includes("BUY");
  const isSell = rec.recommendation_type.includes("SELL");

  const recColor = isBuy ? "text-green-400 border-green-700/50" : isSell ? "text-red-400 border-red-700/50" : "text-yellow-400 border-yellow-700/50";
  const recBg = isBuy ? "bg-green-900/10" : isSell ? "bg-red-900/10" : "bg-yellow-900/10";

  // TASE prices are shown in ₪, US-listed stocks in $
  const currency = rec.symbol.endsWith(".TA") ? "₪" : "$";
  const fmt = (v?: number) =>
    v !== undefined ? `${currency}${v.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "N/A";

  return (
    <div className={`bg-gray-900 rounded-2xl border ${recColor} ${recBg} overflow-hidden`}>
      {/* Header */}
      <div className="p-5">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <span className="text-2xl font-bold">{rec.symbol}</span>
              <span className={`text-sm font-bold px-2 py-0.5 rounded ${isBuy ? "bg-green-800/50" : isSell ? "bg-red-800/50" : "bg-yellow-800/50"} ${recColor.split(" ")[0]}`}>
                {rec.recommendation_type}
              </span>
            </div>
            {rec.asset_name && <p className="text-sm text-gray-400">{rec.asset_name}</p>}
            {(() => {
              // Entry readiness: combine the BUY thesis with the live technical
              // signal into one timing cue. Only for BUY recommendations.
              if (!isBuy) return null;
              const sig = (tech?.timing_signal || rec.technical_analysis?.timing_signal || "").toUpperCase();
              if (!sig) return null;
              if (sig === "BUY_NOW" || sig === "STRONG_BUY") {
                return <span className="inline-block mt-1 mr-1 text-xs px-2 py-0.5 rounded-full bg-green-900/50 text-green-300 border border-green-600/50">🟢 {t("Good entry", "נקודת כניסה טובה")}</span>;
              }
              // WAIT and SELL are NOT the same state and must not share a
              // badge. WAIT means the technical has not confirmed entry yet.
              // SELL means it has actively turned against the position — and
              // that is what the alert says out loud, so a card that answers
              // "wait" contradicts the message that brought the reader here.
              // Being told to sell and then shown "wait for stabilization" is
              // the worst kind of disagreement: two opposite actions, both
              // from the same system, about the same stock, minutes apart.
              if (sig === "SELL_NOW" || sig === "STRONG_SELL") {
                return <span className="inline-block mt-1 mr-1 text-xs px-2 py-0.5 rounded-full bg-red-900/50 text-red-300 border border-red-600/50">🔴 {t("Technical turned negative", "הסיגנל הטכני התהפך לשלילי")}</span>;
              }
              if (sig === "WAIT") {
                return <span className="inline-block mt-1 mr-1 text-xs px-2 py-0.5 rounded-full bg-yellow-900/40 text-yellow-300 border border-yellow-700/40">🟡 {t("Wait for stabilization", "הזדמנות — המתן לייצוב")}</span>;
              }
              return null;
            })()}
            {/* Another listing of the same company.
                Stated rather than hidden. Choosing one and suppressing the
                other would mean acting on an identification that can be
                wrong — and when it is wrong it shows one business under
                another's name. A note costs nothing if it is wrong, and
                tells the reader something true when it is right. */}
            {rec.sibling_listings && rec.sibling_listings.length > 0 && (() => {
              // "Buy whichever is cheaper" is only honest advice if the card
              // shows prices that can be compared. The sibling prices are
              // live; current_price_at_recommendation is not, and a reader
              // comparing those two read a stock that was $2 more expensive
              // as $9 cheaper. So the comparison is made here, against this
              // listing's own live price, or not offered at all.
              const base = typeof rec.current_price === "number" ? rec.current_price : null;
              const priced = rec.sibling_listings.filter(
                (s) => typeof s.last_price === "number"
              ) as Array<{ symbol: string; last_price: number }>;
              const cheapest = base !== null && priced.length
                ? priced.reduce((a, b) => (b.last_price < a.last_price ? b : a))
                : null;
              const siblingWins = cheapest !== null && cheapest.last_price < base!;
              // Under a percent these listings trade back and forth, so
              // naming a winner would send the reader chasing noise.
              const gapPct = cheapest !== null
                ? Math.abs(cheapest.last_price - base!) / base! * 100
                : 0;

              return (
                <p className="mt-1.5 text-[11px] text-gray-400 leading-relaxed">
                  {t(
                    "{company} also trades as ",
                    "{company} נסחרת גם כ-",
                    { company: rec.asset_name || rec.symbol }
                  )}
                  {rec.sibling_listings.map((s, i) => (
                    <React.Fragment key={s.symbol}>
                      {i > 0 && ", "}
                      <span className="font-mono text-gray-300">{s.symbol}</span>
                      {typeof s.last_price === "number" && (
                        <span className="num text-gray-500"> (${s.last_price.toFixed(2)})</span>
                      )}
                    </React.Fragment>
                  ))}
                  {base !== null && (
                    <span className="num text-gray-500">
                      {t(
                        ", against {symbol} at ${price} now",
                        ", מול {symbol} ב-${price} כרגע",
                        { symbol: rec.symbol, price: base.toFixed(2) }
                      )}
                    </span>
                  )}
                  {". "}
                  {t(
                    "Same company, same economics — the difference is voting rights.",
                    "אותה חברה, אותה כלכלה — ההבדל הוא זכות הצבעה."
                  )}
                  {cheapest !== null && gapPct >= 1 && (
                    <>
                      {" "}
                      <span className="text-gray-300">
                        {t(
                          "{symbol} is the cheaper of the two right now.",
                          "{symbol} היא הזולה מבין השתיים כרגע.",
                          { symbol: siblingWins ? cheapest.symbol : rec.symbol }
                        )}
                      </span>
                    </>
                  )}
                  {cheapest !== null && gapPct < 1 && (
                    <>
                      {" "}
                      {t(
                        "They are within a percent of each other — either one is fine.",
                        "הפער ביניהן פחות מאחוז — כל אחת מהן בסדר."
                      )}
                    </>
                  )}
                </p>
              );
            })()}

            {(() => {
              // Risk transparency: short positions and high-volatility stocks
              // carry materially different risk — always label them, whatever
              // the user's display filters are.
              const beta = typeof rec.beta === "number" ? rec.beta : null;
              // Volatility is stated on every card, not only the alarming ones.
              // Showing a badge exclusively for high-risk stocks meant a silent
              // card could mean "calm stock" or "never measured", and the
              // reader had no way to tell which.
              const band =
                beta === null ? null :
                beta < 0.8 ? {
                  label: t("Low volatility", "תנודתיות נמוכה"),
                  cls: "bg-green-950/60 text-green-300 border-green-800/50",
                  icon: "🛡️",
                } :
                beta < 1.3 ? {
                  label: t("Market-like volatility", "תנודתיות רגילה"),
                  cls: "bg-gray-800/80 text-gray-300 border-gray-700",
                  icon: "〰️",
                } :
                beta < 1.8 ? {
                  label: t("High volatility", "תנודתיות גבוהה"),
                  cls: "bg-orange-950/60 text-orange-300 border-orange-800/50",
                  icon: "⚡",
                } : {
                  label: t("Very high volatility", "תנודתיות גבוהה מאוד"),
                  cls: "bg-red-950/60 text-red-300 border-red-800/50",
                  icon: "⚡",
                };
              const betaHint = beta === null ? "" : t(
                "Beta {beta} — moves about {beta}× the market. Measures market-correlated movement only; a calm stock can still gap on its own news.",
                "בטא {beta} — המניה זזה בערך פי {beta} מהשוק. מודד תנועה מול השוק בלבד; מניה רגועה עדיין יכולה לקפוץ על חדשות שלה.",
                { beta: beta.toFixed(2) });
              if (!isSell && !band) return null;
              return (
                <>
                  {isSell && (
                    <span className="inline-block mt-1 mr-1 text-xs px-2 py-0.5 rounded-full bg-red-950/60 text-red-300 border border-red-800/50"
                          title={t("Betting on a decline — unlimited downside", "הימור על ירידת מחיר — הפסד אפשרי בלתי מוגבל")}>
                      📉 {t("Short position", "פוזיציית שורט")}
                    </span>
                  )}
                  {band && (
                    <span className={`inline-block mt-1 mr-1 text-xs px-2 py-0.5 rounded-full border ${band.cls}`}
                          title={betaHint}>
                      {band.icon} {band.label} · β {beta!.toFixed(2)}
                    </span>
                  )}
                </>
              );
            })()}
            {(() => {
              if (!approvedAt) return null;
              const ageDays = Math.floor((Date.now() - new Date(approvedAt).getTime()) / 86400000);
              // Thresholds follow the actual refresh policy. The weekly scan
              // only covers the current pre-screener pool, so a stock that left
              // the pool waits for its quarterly turn; the backend closes that
              // gap by re-queueing any live recommendation past 30 days and
              // retiring it at 45. The badge says which of those states this
              // card is in, so "old" no longer reads as "broken".
              if (ageDays < 7) {
                return <span className="inline-block mt-1 text-xs px-2 py-0.5 rounded-full bg-green-900/40 text-green-300 border border-green-700/40">🟢 {t("Fresh", "עדכנית")}</span>;
              } else if (ageDays <= 30) {
                return <span className="inline-block mt-1 text-xs px-2 py-0.5 rounded-full bg-yellow-900/40 text-yellow-300 border border-yellow-700/40"
                             title={t("Within the refresh cycle — re-analysed within 30 days", "בתוך מחזור הריענון — הניתוח נבדק מחדש עד 30 יום")}>🟡 {t("{days} days", "{days} ימים", { days: ageDays })}</span>;
              } else {
                // Say what the reader should do, not what the system is doing.
                // "Awaiting re-check" is internal state: it tells someone
                // holding a 49-day-old card nothing about whether to act on it.
                return <span className="inline-block mt-1 text-xs px-2 py-0.5 rounded-full bg-orange-900/40 text-orange-300 border border-orange-700/40"
                             title={t(
                               "The target and stop were set {days} days ago, before subsequent price moves and possibly before an earnings report. It is queued for re-analysis and will be retired at 45 days if not re-checked. Until then do not act on these numbers without checking the current price.",
                               "יעד המחיר והסטופ נקבעו לפני {days} ימים, לפני שינויי מחיר ואולי לפני דוח רבעוני. המניה בתור לניתוח מחדש; אם לא תיבדק עד גיל 45 יום ההמלצה תוסר מהפיד. עד אז אל תפעל לפי המספרים האלה בלי לבדוק את המחיר הנוכחי.",
                               { days: ageDays })}>🟠 {t("{days}-day-old analysis — verify price first", "ניתוח בן {days} ימים — אמת מחיר לפני פעולה", { days: ageDays })}</span>;
              }
            })()}
          </div>

          <div className="text-right space-y-1">
            <div className="text-2xl font-bold mb-1">
              {rec.confidence_score.toFixed(0)}%
            </div>
            <p className="text-xs text-gray-400">{t("Confidence", "ביטחון")}</p>
            {(() => {
              const alloc = (rec.fundamental_analysis as any)?.allocation_recommendation;
              if (!alloc || alloc === "NONE") return null;
              const cls = alloc === "HIGH" ? "bg-green-900/40 text-green-300 border-green-700/40"
                : alloc === "MEDIUM" ? "bg-blue-900/40 text-blue-300 border-blue-700/40"
                : "bg-yellow-900/40 text-yellow-300 border-yellow-700/40";
              // The enum value was shown raw to every non-Hebrew reader —
              // "MEDIUM" is a database token, not a label.
              const ALLOCATION: Record<string, [string, string]> = {
                HIGH: ["High allocation", "הקצאה גבוהה"],
                MEDIUM: ["Medium allocation", "הקצאה בינונית"],
                LOW: ["Low allocation", "הקצאה נמוכה"],
              };
              const label = ALLOCATION[alloc] ? t(...ALLOCATION[alloc]) : alloc;
              return (
                <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded border ${cls}`}>
                  {label}
                </span>
              );
            })()}
          </div>
        </div>

        {/* Key Metrics */}
        <div className="grid grid-cols-4 gap-4 mt-4">
          <div>
            {/* Both prices, with the live one leading.
                The entry price is what the target and stop were set against,
                so it cannot be dropped — but it is not what a reader buying
                today pays, and showing it alone put a 33-day-old $344.72
                beside a live sibling quote of $353.33 on a stock that had
                since moved to $355.42. */}
            {(() => {
              const live = typeof rec.current_price === "number" ? rec.current_price : null;
              const entry = rec.current_price_at_recommendation;
              if (live === null) {
                return (
                  <>
                    <p className="text-xs text-gray-400" title={t("The price the analysis was written against, not a live quote", "המחיר שעליו נכתב הניתוח, לא מחיר השוק כרגע")}>
                      {t("Price at recommendation", "מחיר בעת ההמלצה")}
                    </p>
                    <p className="font-bold">{fmt(entry)}</p>
                  </>
                );
              }
              const drift = entry ? ((live - entry) / entry) * 100 : null;
              return (
                <>
                  <p className="text-xs text-gray-400" title={t("The most recent price the system recorded, refreshed on every scan", "המחיר האחרון שהמערכת רשמה, מתעדכן בכל סריקה")}>
                    {t("Current price", "מחיר נוכחי")}
                  </p>
                  <p className="font-bold">{fmt(live)}</p>
                  {entry != null && (
                    <p className="text-[10px] text-gray-500 num" dir="ltr">
                      {t("entry {price}", "בהמלצה {price}", { price: fmt(entry) })}
                      {drift !== null && ` (${drift >= 0 ? "+" : ""}${drift.toFixed(1)}%)`}
                    </p>
                  )}
                </>
              );
            })()}
          </div>
          <div>
            <p className="text-xs text-gray-400">{t("Target", "יעד מחיר")}</p>
            <p className="font-bold text-green-400">{fmt(rec.target_price)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400">{t("Stop Loss", "סטופ לוס")}</p>
            <p className="font-bold text-red-400">{fmt(rec.stop_loss)}</p>
          </div>
          <div>
            {/* Risk/reward, computed from the committee's own target and stop.
                It is arithmetic, not an opinion, so unlike the confidence score
                it genuinely separates one recommendation from another: measured
                over a week of live signals, confidence spans 11 points with a
                standard deviation of 3, which cannot rank anything. */}
            {(() => {
              // Measured from the CURRENT price, not the one the analysis was
              // written against. Those give different answers and only one of
              // them describes the trade on offer: Alphabet's target of $430
              // and stop of $295 read 1:1.7 from the old $344.72 and 1:1.2
              // from today's $355.42. The stock had risen into its target, so
              // the reward shrank and the risk grew — and the figure that
              // exists to rank one trade against another was overstating this
              // one by a third for anyone buying now.
              const entry = typeof rec.current_price === "number"
                ? rec.current_price
                : rec.current_price_at_recommendation;
              const fromLive = typeof rec.current_price === "number";
              const target = rec.target_price;
              const stop = rec.stop_loss;
              if (!entry || !target || !stop) {
                return (
                  <>
                    <p className="text-xs text-gray-400">{t("Risk / reward", "סיכוי מול סיכון")}</p>
                    <p className="font-bold text-gray-600">—</p>
                  </>
                );
              }
              // Once the price has run through one of the two levels, the
              // setup no longer exists and the ratio stops meaning anything:
              // the absolute values would keep producing a confident-looking
              // number out of a target already reached or a stop already
              // broken. Say so instead.
              const isShort = rec.recommendation_type === RecommendationType.SELL
                || rec.recommendation_type === RecommendationType.STRONG_SELL;
              const hitTarget = isShort ? entry <= target : entry >= target;
              const hitStop = isShort ? entry >= stop : entry <= stop;
              if (hitTarget || hitStop) {
                return (
                  <>
                    <p className="text-xs text-gray-400">{t("Risk / reward", "סיכוי מול סיכון")}</p>
                    <p className="font-bold text-gray-500 text-xs leading-tight">
                      {hitTarget
                        ? t("Target reached", "היעד הושג")
                        : t("Past the stop", "עבר את הסטופ")}
                    </p>
                  </>
                );
              }
              const reward = Math.abs(target - entry);
              const risk = Math.abs(entry - stop);
              const ratio = risk > 0 ? reward / risk : null;
              const upPct = (reward / entry) * 100;
              const downPct = (risk / entry) * 100;

              // A stop inside a normal day's movement is not a risk level, and
              // the ratio built on it is not a measure of anything. FISV sat
              // $0.31 above a $46.00 stop: arithmetically 1:84, rendered in
              // green, reading as the best trade on the screen — while the
              // position was two thirds of one percent from being closed by
              // ordinary noise on a stock whose beta is 0.79.
              //
              // The ratio is not shown at all in that state. Dividing by a
              // number this close to zero produces a figure whose size comes
              // from the denominator, not from the opportunity, and no amount
              // of colour makes that honest.
              if (downPct < 2) {
                return (
                  <>
                    <p className="text-xs text-gray-400">{t("Risk / reward", "סיכוי מול סיכון")}</p>
                    <p className="font-bold text-orange-400 text-xs leading-tight">
                      {t("At the stop", "צמוד לסטופ")}
                    </p>
                    <p className="text-[10px] text-gray-500 num" dir="ltr">
                      −{downPct.toFixed(1)}%
                    </p>
                  </>
                );
              }

              const tone =
                ratio === null ? "text-gray-600"
                : ratio >= 2 ? "text-green-400"
                : ratio >= 1.5 ? "text-yellow-400"
                : "text-orange-400";
              const basis = fromLive
                ? t("from the current price", "מהמחיר הנוכחי")
                : t("from the price at recommendation", "ממחיר ההמלצה");
              return (
                <>
                  <p
                    className="text-xs text-gray-400"
                    title={t("Risking {down}% to make {up}% — {basis}",
                             "מסכנים {down}% כדי להרוויח {up}% — {basis}",
                             { down: downPct.toFixed(1), up: upPct.toFixed(1), basis })}
                  >
                    {t("Risk / reward", "סיכוי מול סיכון")}
                  </p>
                  <p className={`font-bold ${tone}`} dir="ltr">
                    {/* Capped, because past about 10:1 the figure is reporting
                        how tight the stop is rather than how good the trade
                        is, and one decimal place on it claims a precision it
                        does not have. "1 : 26.4" and "1 : 84.2" differ only in
                        how close the price sits to the stop; the percentages
                        below already say that, and say it in money. */}
                    {ratio === null ? "—" : ratio > 10 ? "1 : 10+" : `1 : ${ratio.toFixed(1)}`}
                  </p>
                  <p className="text-[10px] text-gray-500 num" dir="ltr">
                    +{upPct.toFixed(0)}% / −{downPct.toFixed(0)}%
                  </p>
                </>
              );
            })()}
          </div>
        </div>

        {/* Senior Notes Preview */}
        {rec.senior_notes && !expanded && (
          <p className="mt-3 text-sm text-gray-300 line-clamp-2">
            {rec.senior_notes}
          </p>
        )}
      </div>

      {/* Expanded Content */}
      {expanded && (
        <div className="border-t border-gray-800 p-5 space-y-4">
          {/* Fundamental Analysis */}
          {rec.fundamental_analysis && (
            <div>
              <h4 className="text-sm font-bold mb-2 text-blue-400">
                {t("Fundamental Analysis", "ניתוח בסיסי")}
              </h4>
              <div className="grid grid-cols-2 gap-3">
                {rec.fundamental_analysis.bull_case && (
                  <div className="bg-green-900/20 rounded-xl p-3">
                    <p className="text-xs text-green-400 font-medium mb-1">{t("Bull Case", "תרחיש חיובי")}</p>
                    <p className="text-xs text-gray-300">{rec.fundamental_analysis.bull_case}</p>
                  </div>
                )}
                {rec.fundamental_analysis.bear_case && (
                  <div className="bg-red-900/20 rounded-xl p-3">
                    <p className="text-xs text-red-400 font-medium mb-1">{t("Bear Case", "תרחיש שלילי")}</p>
                    <p className="text-xs text-gray-300">{rec.fundamental_analysis.bear_case}</p>
                  </div>
                )}
              </div>
              {rec.fundamental_analysis.risk_factors?.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-gray-400 mb-1">{t("Risk Factors", "גורמי סיכון")}</p>
                  <ul className="space-y-1">
                    {rec.fundamental_analysis.risk_factors.map((r, i) => (
                      <li key={i} className="text-xs text-gray-300 flex items-start gap-1">
                        <span className="text-red-400 mt-0.5">•</span> {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Sentiment */}
          {rec.sentiment_data && (
            <div>
              <h4 className="text-sm font-bold mb-2 text-purple-400">
                {t("Social Sentiment", "סנטימנט חברתי")}
              </h4>
              <div className="flex items-center gap-4">
                <div>
                  <p className="text-xs text-gray-400">{t("Score", "ציון")}</p>
                  <p className={`font-bold ${rec.sentiment_data.score > 0 ? "text-green-400" : rec.sentiment_data.score < 0 ? "text-red-400" : "text-gray-400"}`}>
                    {rec.sentiment_data.score > 0 ? "+" : ""}{rec.sentiment_data.score.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">{t("Mentions", "אזכורים")}</p>
                  <p className="font-bold">{rec.sentiment_data.mentions.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">{t("Trending", "טרנד")}</p>
                  <p className={`font-bold ${rec.sentiment_data.trending ? "text-green-400" : "text-gray-400"}`}>
                    {rec.sentiment_data.trending ? "✓" : "—"}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Senior Notes */}
          {rec.senior_notes && (
            <div>
              <h4 className="text-sm font-bold mb-2 text-yellow-400">
                {t("Senior Committee", "ועדת בכירים")}
              </h4>
              <p className="text-xs text-gray-300">{rec.senior_notes}</p>
            </div>
          )}

          {/* Technical Analysis */}
          {(tech || rec.technical_analysis) && (
            <div>
              <h4 className="text-sm font-bold mb-2 text-cyan-400">
                {t("Technical Analysis", "ניתוח טכני")}
              </h4>
              {(() => {
                // Named `ta`, not `t`: as `t` it shadowed the translator, which
                // is why these three labels were the only ones on the card that
                // could not be translated.
                const ta = tech || rec.technical_analysis;
                if (!ta) return null;
                return (
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { label: "RSI", value: ta.rsi_14?.toFixed(1) },
                      { label: t("Signal", "סיגנל"), value: ta.timing_signal },
                      { label: t("Score", "ציון"), value: `${ta.technical_score}/100` },
                    ].map((item) => (
                      <div key={item.label} className="bg-gray-800 rounded-lg p-2 text-center">
                        <p className="text-xs text-gray-400">{item.label}</p>
                        <p className="font-bold text-sm">{item.value || "N/A"}</p>
                      </div>
                    ))}
                  </div>
                );
              })()}
            </div>
          )}
        </div>
      )}

      {/* Actions.
          Wraps. Six buttons in one non-wrapping row fit only when every label
          is short, so the row silently depended on the length of Hebrew: in
          French "Suivre pour l'entrée" pushed the primary action off the
          right edge with nothing to scroll, and the button a reader needs
          most was the one they could not reach. Wrapping costs a line of
          height and cannot be defeated by a longer word in any language. */}
      <div className="px-5 pb-5 flex flex-wrap items-center gap-2">
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-gray-400 hover:text-white border border-gray-700 rounded-lg px-3 py-1.5"
        >
          {expanded ? (t("Collapse", "הסתר")) : (t("Details", "פרטים"))}
        </button>
        <button
          onClick={() => navigate(`/technical/${rec.id}`)}
          className="text-xs bg-cyan-900/20 border border-cyan-700/50 text-cyan-400 rounded-lg px-3 py-1.5 hover:bg-cyan-900/40"
        >
          {t("Technical", "ניתוח טכני")}
        </button>
        <button
          onClick={() => navigate(`/research/${rec.id}`)}
          className="text-xs bg-yellow-900/20 border border-yellow-700/50 text-yellow-400 rounded-lg px-3 py-1.5 hover:bg-yellow-900/40"
        >
          {t("Research", "מחקר מלא")}
        </button>
        {/* Pushes the primary action right only where there is room for it.
            On a phone it would consume the line and force a wrap with nothing
            on it. */}
        <div className="hidden sm:block flex-1" />
        {(() => {
          if (!isBuy) return null;
          const sig = (tech?.timing_signal || rec.technical_analysis?.timing_signal || "").toUpperCase();
          const positive = sig === "BUY_NOW" || sig === "STRONG_BUY";
          if (positive) return null;  // already a good entry — no need to wait
          return followMsg ? (
            <span className="text-xs text-green-400 px-2">{t("✓ Following", "✓ במעקב — נודיע בכניסה")}</span>
          ) : (
            <button
              onClick={handleFollowForEntry}
              disabled={following}
              className="text-xs bg-blue-900/20 border border-blue-700/50 text-blue-300 rounded-lg px-3 py-1.5 hover:bg-blue-900/40 disabled:opacity-60"
              title={t("We'll alert you when the technical confirms an entry point", "נודיע לך כשהניתוח הטכני יאשר נקודת כניסה")}
            >
              {following ? "..." : `👁 ${t("Follow for entry", "עקוב לנקודת כניסה")}`}
            </button>
          );
        })()}
        {isBuy || (!isSell) ? (
          <button
            onClick={onBuy}
            className="bg-green-600 hover:bg-green-700 text-white rounded-lg px-4 py-1.5 text-sm font-medium"
          >
            {t("Add to Portfolio", "מחזיק? הוסף לתיק")}
          </button>
        ) : null}
        {isSell && (
          <button
            onClick={onSell}
            className="bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-1.5 text-sm font-medium"
          >
            {t("Sell", "מכור")}
          </button>
        )}
        <button
          onClick={onDismiss}
          className="text-gray-500 hover:text-gray-300 text-sm px-2"
        >
          ✕
        </button>
      </div>
    </div>
  );
};

export default RecommendationCard;
