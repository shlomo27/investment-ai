/**
 * The market as a whole: healthy, correcting or under stress.
 *
 * Every signal in the app is about one stock; this is the one reading about
 * everything at once. It shows the regime and the main reasons behind it, so
 * the reader can see why, and says plainly that it is risk information, not
 * an instruction to sell.
 */
import React from "react";
import { Link } from "react-router-dom";
import { type MarketRegimeReason } from "../../api/client";
import { useMarketRegime, useLatestMarketReading } from "./useMarketRegime";
import { useT, type TFunction } from "../../i18n/t";

// Direct t() calls: the string scanner only sees literals passed to t().
export function reasonText(t: TFunction, r: MarketRegimeReason): string {
  const v = r.vars ?? {};
  switch (r.code) {
    case "spy_below_200": return t("S&P 500 is below its 200-day average", "S&P 500 מתחת לממוצע 200 הימים");
    case "spy_below_50": return t("S&P 500 is below its 50-day average", "S&P 500 מתחת לממוצע 50 הימים");
    case "drawdown_bear": return t("S&P 500 is {pct}% below its one-year high (bear market)", "S&P 500 נמוך ב-{pct}% מהשיא השנתי (שוק דובי)", v);
    case "drawdown_correction": return t("S&P 500 is {pct}% below its one-year high (correction)", "S&P 500 נמוך ב-{pct}% מהשיא השנתי (תיקון)", v);
    case "vix_extreme": return t("VIX at {v}: extreme fear", "VIX ב-{v}: פחד קיצוני", v);
    case "vix_elevated": return t("VIX at {v}: elevated fear", "VIX ב-{v}: פחד מוגבר", v);
    case "hy_stress": return t("High-yield credit spread at {v}%: credit stress", "מרווח אשראי בתשואה גבוהה {v}%: לחץ אשראי", v);
    case "hy_elevated": return t("High-yield credit spread at {v}%: elevated", "מרווח אשראי בתשואה גבוהה {v}%: גבוה", v);
    case "hy_widening": return t("Credit spreads widened {v} points in a month", "מרווחי האשראי התרחבו ב-{v} נקודות בחודש", v);
    case "fsi_high": return t("Financial stress index at {v}: high", "מדד הלחץ הפיננסי {v}: גבוה", v);
    case "fsi_above": return t("Financial stress index at {v}: above normal", "מדד הלחץ הפיננסי {v}: מעל הרגיל", v);
    case "nfci_tight": return t("Financial conditions tighter than average (NFCI {v})", "התנאים הפיננסיים הדוקים מהממוצע (NFCI {v})", v);
    case "curve_inverted": return t("Yield curve inverted (10Y-2Y {v})", "עקום התשואות הפוך (10Y-2Y {v})", v);
    case "curve_uninverted": return t("Yield curve has just come out of an inversion, which has preceded past recessions", "עקום התשואות יצא לאחרונה מהיפוך, מצב שקדם למיתונים בעבר");
    case "breadth_low": return t("Only {pct}% of analysed stocks are above their 200-day average", "רק {pct}% מהמניות המנותחות מעל ממוצע 200 הימים", v);
    case "breadth_weak": return t("{pct}% of analysed stocks are above their 200-day average", "{pct}% מהמניות המנותחות מעל ממוצע 200 הימים", v);
    case "global_broad_weak": return t("{n} of {total} world regions are below their 200-day average", "{n} מתוך {total} אזורים בעולם מתחת לממוצע 200 הימים", v);
    case "global_weak": return t("{n} of {total} world regions are below their 200-day average", "{n} מתוך {total} אזורים בעולם מתחת לממוצע 200 הימים", v);
    case "region_bear": return t("{region} is {pct}% below its one-year high (bear market)", "{region} נמוך ב-{pct}% מהשיא השנתי (שוק דובי)",
                                 { ...v, region: regionName(t, String(v.region)) });
    case "smallcaps_below_200": return t("US small caps are below their 200-day average", "המניות הקטנות בארה״ב מתחת לממוצע 200 הימים");
    case "eu_hy_stress": return t("European high-yield spread at {v}%: credit stress", "מרווח אשראי בתשואה גבוהה באירופה {v}%: לחץ אשראי", v);
    case "eu_hy_elevated": return t("European high-yield spread at {v}%: elevated", "מרווח אשראי בתשואה גבוהה באירופה {v}%: גבוה", v);
    case "dollar_surge": return t("The dollar rose {v}% in a month: money running for safety", "הדולר עלה {v}% בחודש: כסף בורח למקום בטוח", v);
    case "yen_surge": return t("The yen rose {v}% in a month: carry trades unwinding", "הין עלה {v}% בחודש: פירוק עסקאות מימון בין", v);
    // A reason without a code (from an older reading): its own Hebrew or
    // English text, rather than English for everyone.
    default: return t(r.en, r.he);
  }
}

export function regionName(t: TFunction, region: string): string {
  return region === "europe" ? t("Europe", "אירופה")
    : region === "japan" ? t("Japan", "יפן")
    : region === "china" ? t("China", "סין")
    : region === "emerging" ? t("Emerging markets", "שווקים מתעוררים")
    : region === "smallcaps" ? t("US small caps", "מניות קטנות בארה״ב")
    : region;
}

const MarketRegimeCard: React.FC = () => {
  const t = useT();
  const reading = useMarketRegime();
  const latest = useLatestMarketReading();

  // Nothing until there is a reading: an empty gauge would read as "healthy".
  if (!reading) return null;

  const style =
    reading.regime === "STRESS"
      ? { dot: "🔴", label: t("Market under stress", "השוק בלחץ"), cls: "border-red-700/50 bg-red-950/30", text: "text-red-300" }
      : reading.regime === "CORRECTION"
      ? { dot: "🟡", label: t("Market in correction", "השוק בתיקון"), cls: "border-yellow-700/50 bg-yellow-950/20", text: "text-yellow-300" }
      : { dot: "🟢", label: t("Market healthy", "שוק בריא"), cls: "border-green-800/50 bg-green-950/20", text: "text-green-300" };

  const top = [...reading.reasons].sort((a, b) => b.points - a.points).slice(0, 3);

  return (
    // The whole card opens the Market tab, where every measure is shown.
    <Link to="/market" className={`block rounded-2xl border p-4 ${style.cls}`}>
      <div className="flex items-center justify-between gap-3">
        <p className={`font-bold ${style.text}`}>
          {style.dot} {style.label}
        </p>
        <span className="text-[11px] text-gray-500">{t("Whole market", "השוק כולו")}</span>
      </div>
      {top.length > 0 ? (
        <ul className="mt-2 space-y-1 text-xs text-gray-300">
          {top.map((r) => (
            <li key={r.code || r.en}>• {reasonText(t, r)}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs text-gray-400">
          {t("Trend, credit and stress measures are all within normal ranges.", "מדדי המגמה, האשראי והלחץ כולם בטווח הרגיל.")}
        </p>
      )}
      {reading.regime !== "HEALTHY" && (
        <p className="mt-2 text-[11px] text-gray-500 leading-relaxed">
          {t("This is risk information, not an instruction to sell. Whether to keep holding a stock depends on its stop loss.",
             "זהו מידע על רמת הסיכון ולא הוראה למכור. ההחלטה אם להמשיך להחזיק מניה תלויה בסטופ שלה.")}
        </p>
      )}
      {latest && latest.regime !== reading.regime && (
        // Same note as the Market tab: the newest reading disagrees with the
        // confirmed state, and the card must not read calmer than the page.
        <p className="mt-2 text-xs text-gray-300">
          {t("The latest reading points to: {r}, pending confirmation.", "הקריאה האחרונה מצביעה על: {r}, ממתין לאישור.",
             { r: latest.regime === "STRESS" ? t("Market under stress", "השוק בלחץ")
                : latest.regime === "CORRECTION" ? t("Market in correction", "השוק בתיקון")
                : t("Market healthy", "שוק בריא") })}
        </p>
      )}
      <p className="mt-2 text-[11px] text-blue-400">{t("Full market analysis →", "ניתוח השוק המלא ←")}</p>
    </Link>
  );
};

export default MarketRegimeCard;
