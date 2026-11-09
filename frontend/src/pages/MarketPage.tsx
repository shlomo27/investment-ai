/**
 * The market as a whole.
 *
 * Every other screen is about single stocks. This one answers the question
 * underneath all of them — is the market itself healthy, correcting, or
 * under stress — and shows its working: every measure checked, its value,
 * the level at which it counts against the market, a year of history, the
 * past changes of regime with what the index did next, and which of the
 * reader's own stocks are most exposed.
 */
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { marketApi, type MarketRegimeDetail, type MarketIndicator } from "../api/client";
import { useT, useDir, useLocale, type TFunction } from "../i18n/t";
import { reasonText, regionName } from "../components/Market/MarketRegimeCard";

const REGIME_STYLE = {
  STRESS: { dot: "🔴", cls: "border-red-700/50 bg-red-950/30", text: "text-red-300" },
  CORRECTION: { dot: "🟡", cls: "border-yellow-700/50 bg-yellow-950/20", text: "text-yellow-300" },
  HEALTHY: { dot: "🟢", cls: "border-green-800/50 bg-green-950/20", text: "text-green-300" },
} as const;

function regimeLabel(t: TFunction, r?: string | null): string {
  return r === "STRESS" ? t("Market under stress", "השוק בלחץ")
    : r === "CORRECTION" ? t("Market in correction", "השוק בתיקון")
    : r === "HEALTHY" ? t("Market healthy", "שוק בריא")
    : "—";
}

// Direct t() calls: the string scanner only sees literals passed to t().
function indicatorInfo(t: TFunction, key: string): { name: string; why: string } {
  switch (key) {
    case "spy_vs_200": return { name: t("S&P 500 vs its 200-day average", "S&P 500 מול ממוצע 200 הימים"),
      why: t("The long-term trend. Below it, the market's main trend has turned down.", "המגמה ארוכת הטווח. מתחתיו, המגמה הראשית של השוק התהפכה לירידה.") };
    case "spy_vs_50": return { name: t("S&P 500 vs its 50-day average", "S&P 500 מול ממוצע 50 הימים"),
      why: t("The medium-term trend: the first to turn in a pullback.", "המגמה בטווח הבינוני: הראשונה להתהפך בירידה.") };
    case "drawdown": return { name: t("Distance from the one-year high", "מרחק מהשיא השנתי"),
      why: t("10% down is a correction; 20% is a bear market.", "ירידה של 10% היא תיקון; 20% היא שוק דובי.") };
    case "vix": return { name: t("VIX (fear index)", "VIX (מדד הפחד)"),
      why: t("The volatility investors expect. It jumps when they are afraid.", "התנודתיות שהמשקיעים צופים. קופץ כשהם מפחדים.") };
    case "hy_spread": return { name: t("High-yield credit spread", "מרווח אשראי בתשואה גבוהה"),
      why: t("What lenders charge weaker companies above government bonds. It widened for months before the 2008 crash.", "כמה מלווים דורשים מחברות חלשות מעבר לאג״ח ממשלתיות. הוא התרחב חודשים לפני הקריסה של 2008.") };
    case "hy_widening_1m": return { name: t("Credit spread change, last month", "שינוי במרווח האשראי, חודש אחרון"),
      why: t("Speed matters: a fast widening is an early warning.", "המהירות קובעת: התרחבות מהירה היא אזהרה מוקדמת.") };
    case "stlfsi": return { name: t("Financial stress index (St. Louis Fed)", "מדד הלחץ הפיננסי (הפד של סנט לואיס)"),
      why: t("0 is normal. Above 0, the financial system is under more stress than usual.", "0 הוא מצב רגיל. מעל 0, המערכת הפיננסית בלחץ גבוה מהרגיל.") };
    case "nfci": return { name: t("Financial conditions (Chicago Fed NFCI)", "תנאים פיננסיים (NFCI של הפד בשיקגו)"),
      why: t("Above 0, credit is harder to get than usual.", "מעל 0, קשה יותר מהרגיל להשיג אשראי.") };
    case "yield_curve": return { name: t("Yield curve (10-year minus 2-year)", "עקום התשואות (10 שנים פחות שנתיים)"),
      why: t("Inverted, or just back from an inversion, it has preceded past recessions. A slow signal: months, not days.", "עקום הפוך, או כזה שבדיוק חזר מהיפוך, קדם למיתונים בעבר. סימן איטי: חודשים, לא ימים.") };
    case "breadth": return { name: t("Analysed stocks above their 200-day average", "מניות מנותחות מעל ממוצע 200 הימים"),
      why: t("How many stocks share the trend. A fall in everything is worse than a fall in a few giants.", "כמה מניות שותפות למגמה. ירידה של כולן חמורה מירידה של כמה ענקיות.") };
    case "region_europe": case "region_japan": case "region_china": case "region_emerging":
      return { name: t("{region} vs its 200-day average", "{region} מול ממוצע 200 הימים", { region: regionName(t, key.slice(7)) }),
        why: t("Read through the region's main US-listed fund. A crisis abroad can reach the US later.", "נמדד דרך קרן הסל המרכזית של האזור. משבר בחו״ל יכול להגיע לארה״ב מאוחר יותר.") };
    case "region_smallcaps": return { name: t("US small caps vs their 200-day average", "מניות קטנות בארה״ב מול ממוצע 200 הימים"),
      why: t("Small companies tend to weaken before the big index.", "חברות קטנות נוטות להיחלש לפני המדד הגדול.") };
    case "eu_hy_spread": return { name: t("European high-yield credit spread", "מרווח אשראי בתשואה גבוהה באירופה"),
      why: t("Credit stress in Europe, the first sign in the 2011 debt crisis.", "לחץ אשראי באירופה, הסימן הראשון במשבר החוב של 2011.") };
    case "dollar_1m": return { name: t("US dollar, last month", "הדולר האמריקאי, חודש אחרון"),
      why: t("In a crisis money runs to the dollar; a sharp rise is a sign of fear.", "במשבר כסף בורח לדולר; עלייה חדה היא סימן לפחד.") };
    case "yen_1m": return { name: t("Japanese yen, last month", "הין היפני, חודש אחרון"),
      why: t("A sudden jump in the yen forces investors who borrowed in yen to sell, as in August 2024.", "קפיצה פתאומית בין מאלצת משקיעים שלוו בין למכור, כמו באוגוסט 2024.") };
    default: return { name: key, why: "" };
  }
}

function fmtValue(key: string, v: number | null): string {
  if (v === null || v === undefined) return "—";
  if (key === "spy_vs_200" || key === "spy_vs_50" || key.startsWith("region_") || key === "dollar_1m" || key === "yen_1m")
    return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
  if (key === "eu_hy_spread") return `${v.toFixed(2)}%`;
  if (key === "drawdown") return `-${v.toFixed(1)}%`;
  if (key === "hy_spread") return `${v.toFixed(2)}%`;
  if (key === "hy_widening_1m") return `${v > 0 ? "+" : ""}${v.toFixed(2)}`;
  if (key === "breadth") return `${Math.round(v)}%`;
  if (key === "vix") return v.toFixed(1);
  return v.toFixed(2);
}

function thresholdText(t: TFunction, ind: MarketIndicator): string {
  switch (ind.key) {
    case "spy_vs_200": case "spy_vs_50": return t("Warning below 0%", "אזהרה מתחת ל-0%");
    case "drawdown": return t("Correction from 10% · bear market from 20%", "תיקון מ-10% · שוק דובי מ-20%");
    case "vix": return t("Warning from 25 · alarm from 35", "אזהרה מ-25 · אזעקה מ-35");
    case "hy_spread": return t("Warning from 5% · alarm from 7%", "אזהרה מ-5% · אזעקה מ-7%");
    case "hy_widening_1m": return t("Warning from +1.0 in a month", "אזהרה מ-1.0+ בחודש");
    case "stlfsi": return t("Warning above 0 · alarm from 1.5", "אזהרה מעל 0 · אזעקה מ-1.5");
    case "nfci": return t("Warning above 0", "אזהרה מעל 0");
    case "yield_curve": return ind.note === "uninverted"
      ? t("Just came out of an inversion", "יצא לאחרונה מהיפוך")
      : t("Warning below 0 (inverted)", "אזהרה מתחת ל-0 (הפוך)");
    case "breadth": return t("Warning below 40% · alarm below 25%", "אזהרה מתחת ל-40% · אזעקה מתחת ל-25%");
    case "region_europe": case "region_japan": case "region_china": case "region_emerging": case "region_smallcaps":
      return ind.drawdown != null
        ? t("Warning below 0% · alarm in a bear market (20% off the high; now {d}% off)", "אזהרה מתחת ל-0% · אזעקה בשוק דובי (20% מהשיא; כרגע {d}%)", { d: ind.drawdown })
        : t("Warning below 0% · alarm in a bear market (20% off the high)", "אזהרה מתחת ל-0% · אזעקה בשוק דובי (20% מהשיא)");
    case "eu_hy_spread": return t("Warning from 5% · alarm from 7%", "אזהרה מ-5% · אזעקה מ-7%");
    case "dollar_1m": return t("Warning from +3% in a month", "אזהרה מ-3%+ בחודש");
    case "yen_1m": return t("Warning from +5% in a month", "אזהרה מ-5%+ בחודש");
    default: return "";
  }
}

const StatusPill: React.FC<{ status: MarketIndicator["status"] }> = ({ status }) => {
  const t = useT();
  const s = status === "alert" ? { c: "bg-red-900/50 text-red-300 border-red-700/50", l: t("Alarm", "אזעקה") }
    : status === "warn" ? { c: "bg-yellow-900/40 text-yellow-300 border-yellow-700/40", l: t("Warning", "אזהרה") }
    : status === "ok" ? { c: "bg-green-900/40 text-green-300 border-green-700/40", l: t("Normal", "תקין") }
    : { c: "bg-gray-800 text-gray-400 border-gray-700", l: t("No data", "אין נתון") };
  return <span className={`shrink-0 text-[11px] px-2 py-0.5 rounded-full border ${s.c}`}>{s.l}</span>;
};

const Chart: React.FC<{
  title: string; data: { d: string; v: number | null; a?: number | null; b?: number | null }[];
  refs?: { y: number; color: string }[]; legend?: React.ReactNode; locale: string;
}> = ({ title, data, refs = [], legend, locale }) => {
  if (data.length < 2) return null;
  const fmtDate = (d: string) => new Date(d).toLocaleDateString(locale, { month: "short" });
  return (
    <div className="bg-gray-900 rounded-2xl border border-gray-800 p-4">
      <p className="text-sm font-semibold text-gray-200 mb-1">{title}</p>
      {legend}
      {/* Charts read left to right in every language. */}
      <div dir="ltr" className="h-44 mt-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
            <XAxis dataKey="d" tickFormatter={fmtDate} minTickGap={40} tick={{ fill: "#6b7280", fontSize: 10 }} />
            {/* The threshold lines are the point of these charts, so the
                scale always reaches the highest one, even in a calm year. */}
            <YAxis
              domain={[
                (min: number) => Math.floor(min * 0.95),
                (max: number) => Math.ceil(Math.max(max, ...refs.map((r) => r.y * 1.05))),
              ]}
              tick={{ fill: "#6b7280", fontSize: 10 }} width={44} />
            <Tooltip contentStyle={{ background: "#111827", border: "1px solid #374151", fontSize: 12 }}
                     labelFormatter={(d) => new Date(String(d)).toLocaleDateString(locale)} />
            {refs.map((r) => <ReferenceLine key={r.y} y={r.y} stroke={r.color} strokeDasharray="4 4" />)}
            <Line type="monotone" dataKey="v" stroke="#60a5fa" dot={false} strokeWidth={1.8} isAnimationActive={false} />
            <Line type="monotone" dataKey="a" stroke="#f59e0b" dot={false} strokeWidth={1.2} isAnimationActive={false} />
            <Line type="monotone" dataKey="b" stroke="#ef4444" dot={false} strokeWidth={1.2} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

/** A section that opens on tap. Its header always shows how it stands, so
 *  a closed section still says whether it is worth opening. */
const Section: React.FC<{ title: string; sub?: string; badge?: React.ReactNode; children: React.ReactNode }> = (
  { title, sub, badge, children }) => (
  <details className="group bg-gray-900 rounded-2xl border border-gray-800">
    <summary className="list-none cursor-pointer select-none p-4 flex items-center justify-between gap-3">
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-gray-200">{title}</span>
        {sub && <span className="block text-[11px] text-gray-500">{sub}</span>}
      </span>
      <span className="flex items-center gap-2 shrink-0">
        {badge}
        <span className="text-gray-500 transition-transform group-open:rotate-180">▾</span>
      </span>
    </summary>
    <div className="px-4 pb-4">{children}</div>
  </details>
);

/** How a layer stands, for its closed header: "all normal", "2 of 5 warning". */
const LayerBadge: React.FC<{ rows: MarketIndicator[] }> = ({ rows }) => {
  const t = useT();
  const known = rows.filter((r) => r.status !== "unknown");
  const alerts = known.filter((r) => r.status === "alert").length;
  const warns = known.filter((r) => r.status === "warn").length;
  if (!known.length) return <span className="text-[11px] text-gray-500">{t("No data", "אין נתון")}</span>;
  if (!alerts && !warns) return <span className="text-[11px] px-2 py-0.5 rounded-full border bg-green-900/40 text-green-300 border-green-700/40">🟢 {t("All normal", "הכול תקין")}</span>;
  // Both counts, always: showing only the alarms hid the warnings, so a
  // section with 1 alarm and 3 warnings read as calmer than one with 3.
  return (
    <span className="flex flex-col items-end gap-1">
      {alerts > 0 && <span className="text-[11px] px-2 py-0.5 rounded-full border bg-red-900/50 text-red-300 border-red-700/50">🔴 {t("{n} of {total} in alarm", "{n} מתוך {total} באזעקה", { n: alerts, total: known.length })}</span>}
      {warns > 0 && <span className="text-[11px] px-2 py-0.5 rounded-full border bg-yellow-900/40 text-yellow-300 border-yellow-700/40">🟡 {t("{n} of {total} warning", "{n} מתוך {total} באזהרה", { n: warns, total: known.length })}</span>}
    </span>
  );
};

/** The plain-language summary at the top. Built from the readings by fixed
 *  rules rather than written by a model, so it always matches the numbers
 *  below it, costs nothing, and exists in every language. */
function buildSummary(t: TFunction, d: MarketRegimeDetail): string[] {
  // The summary describes the newest reading, the same one the sections
  // below show. The headline keeps the confirmed state, and says so when the
  // newest reading points elsewhere.
  const cur = d.latest ?? d.current!;
  const lines: string[] = [];
  const of = (layer: string) => d.indicators.filter((i) => i.layer === layer);
  const bad = (rows: MarketIndicator[], level: "warn" | "alert") =>
    rows.filter((r) => (level === "alert" ? r.status === "alert" : r.status === "warn" || r.status === "alert")).length;
  const stress = of("stress");
  const regions = of("global").filter((i) => /^region_(europe|japan|china|emerging)$/.test(i.key) && i.status !== "unknown");
  const weakRegions = regions.filter((i) => i.status !== "ok").length;

  // Every measure at a glance, warnings and alarms both, and how the state
  // is decided: a measure in warning does not by itself make a correction.
  const known = d.indicators.filter((i) => i.status !== "unknown");
  const alarms = known.filter((i) => i.status === "alert").length;
  const warnings = known.filter((i) => i.status === "warn").length;
  lines.push(t("Of {total} measures: {a} in alarm, {w} in warning, the rest normal.",
               "מתוך {total} מדדים: {a} באזעקה, {w} באזהרה, והשאר תקינים.",
               { total: known.length, a: alarms, w: warnings }));
  lines.push(t("Risk score {s}. The market counts as in correction from 3 and under stress from 7; each measure adds 1-2 points.",
               "ציון סיכון {s}. השוק נחשב בתיקון מ-3 ובלחץ מ-7; כל מדד מוסיף 1-2 נקודות.",
               { s: cur.score }));

  // What is driving it.
  // The world-regions count gets its own line below; not repeated here.
  const ownLine = regions.length && weakRegions >= 2 ? ["global_weak", "global_broad_weak"] : [];
  const top = [...cur.reasons].filter((r) => !ownLine.includes(r.code ?? ""))
    .sort((a, b) => b.points - a.points).slice(0, 2).map((r) => reasonText(t, r));
  // In a healthy market the points found are things to note, not reasons.
  lines.push(top.length
    ? (cur.regime === "HEALTHY"
        ? t("Worth noting: {r}.", "כדאי לשים לב: {r}.", { r: top.join("; ") })
        : t("Main reasons: {r}.", "הסיבות העיקריות: {r}.", { r: top.join("; ") }))
    : t("Trend, credit and stress measures are all within normal ranges.", "מדדי המגמה, האשראי והלחץ כולם בטווח הרגיל."));

  // How deep it goes: credit and financial stress, and abroad.
  if (bad(stress, "alert") > 0) {
    lines.push(t("Credit and financial-stress measures are flashing: the kind of signal that came before past crises.",
                 "מדדי האשראי והלחץ הפיננסי מהבהבים: סימן מהסוג שקדם למשברים קודמים."));
  } else if (cur.regime !== "HEALTHY" && bad(stress, "warn") === 0) {
    lines.push(t("Credit and financial-stress measures are still normal: no sign of a financial crisis.",
                 "מדדי האשראי והלחץ הפיננסי עדיין תקינים: אין סימן למשבר פיננסי."));
  }
  if (regions.length && weakRegions >= 2) {
    lines.push(t("The weakness is global: {n} of {total} world regions are falling.",
                 "החולשה עולמית: {n} מתוך {total} אזורים בעולם בירידה.", { n: weakRegions, total: regions.length }));
  } else if (regions.length && cur.regime !== "HEALTHY" && weakRegions === 0) {
    lines.push(t("Markets abroad are holding up: the weakness is mainly in the US.",
                 "השווקים בעולם מחזיקים מעמד: החולשה בעיקר בארה״ב."));
  }

  // What it means for this reader.
  const ex = d.exposure;
  if (ex.followed > 0) {
    if (ex.near_stop.length) {
      // Phrased to read right for one stock or several.
      lines.push(t("For you, near the stop loss: {list}.", "בשבילך, קרוב לסטופ: {list}.",
                   { list: ex.near_stop.map((x) => x.symbol).join(", ") }));
    } else {
      lines.push(t("For you: none of your stocks is near its stop loss.", "בשבילך: אף מניה שלך אינה קרובה לסטופ."));
    }
    if (ex.volatile.length && cur.regime !== "HEALTHY") {
      lines.push(t("Highly volatile, usually hit harder in a fall: {list}.", "תנודתיות גבוהה, בדרך כלל נפגעות יותר בירידות: {list}.",
                   { list: ex.volatile.map((x) => x.symbol).join(", ") }));
    }
  }

  // What to watch next.
  lines.push(
    cur.regime === "STRESS"
      ? t("To watch: a recovery usually shows first in VIX falling and credit spreads narrowing.",
          "למה לשים לב: התאוששות נראית בדרך כלל קודם בירידת ה-VIX ובהצטמצמות מרווחי האשראי.")
      : cur.regime === "CORRECTION" && bad(stress, "warn") === 0
      ? t("To watch: if credit spreads start widening, the risk rises.",
          "למה לשים לב: אם מרווחי האשראי יתחילו להתרחב, הסיכון יעלה.")
      : cur.regime === "CORRECTION"
      ? t("To watch: credit spreads and the stress index. If they keep rising, the market may move to stress.",
          "למה לשים לב: מרווחי האשראי ומדד הלחץ. אם ימשיכו לעלות, השוק עלול לעבור למצב לחץ.")
      : t("Nothing stands out. Trouble usually shows first in credit spreads and VIX.",
          "שום דבר לא בולט. בעיות מופיעות בדרך כלל קודם במרווחי האשראי וב-VIX."),
  );
  return lines;
}

const MarketPage: React.FC = () => {
  const t = useT();
  const dir = useDir();
  const locale = useLocale();
  const [data, setData] = useState<MarketRegimeDetail | null | undefined>(undefined);

  useEffect(() => {
    marketApi.getRegimeDetail().then(setData).catch(() => setData(null));
  }, []);

  if (data === undefined) {
    return <div dir={dir} className="text-gray-500 text-sm p-6">{t("Loading...", "טוען...")}</div>;
  }
  const cur = data?.current;
  if (!data || !cur) {
    return (
      <div dir={dir} className="space-y-4">
        <h1 className="text-2xl font-bold">{t("Market", "שוק")}</h1>
        <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6 text-sm text-gray-400">
          {t("The first market reading is taken after the US close. Check back tomorrow.",
             "הקריאה הראשונה של מצב השוק נעשית אחרי סגירת המסחר בארה״ב. בדוק שוב מחר.")}
        </div>
      </div>
    );
  }

  const style = REGIME_STYLE[cur.regime] ?? REGIME_STYLE.HEALTHY;
  const date = (iso?: string | null) => (iso ? new Date(iso).toLocaleDateString(locale, { day: "numeric", month: "long", year: "numeric" }) : "");
  const layers: { key: MarketIndicator["layer"]; title: string; sub: string }[] = [
    { key: "trend", title: t("Trend", "מגמה"), sub: t("Where the index is heading", "לאן המדד הולך") },
    { key: "stress", title: t("Crisis detectors", "גלאי משבר"), sub: t("The measures that moved before the index in past crises", "המדדים שזזו לפני המדד במשברים קודמים") },
    { key: "global", title: t("Global", "עולמי"), sub: t("Europe, Asia, emerging markets, small caps, the dollar and the yen", "אירופה, אסיה, שווקים מתעוררים, מניות קטנות, הדולר והין") },
    { key: "breadth", title: t("Breadth", "רוחב השוק"), sub: t("How many stocks share the move", "כמה מניות שותפות לתנועה") },
  ];
  // Isolated left-to-right, so a minus sign stays in front of the number
  // inside a right-to-left sentence.
  const pct = (v: number | null) => (v === null ? "—" : `\u2066${v > 0 ? "+" : ""}${v.toFixed(1)}%\u2069`);
  const s = data.series;
  const summary = buildSummary(t, data);

  return (
    <div dir={dir} className="space-y-4">
      <h1 className="text-2xl font-bold">{t("Market", "שוק")}</h1>

      {/* 1. The summary: what a reader needs in two seconds. */}
      <div className={`rounded-2xl border p-4 ${style.cls}`}>
        <p className={`text-lg font-bold ${style.text}`}>
          {style.dot} {regimeLabel(t, cur.regime)}
          {cur.since && <span className="text-sm font-normal text-gray-400"> · {t("since {date}", "מאז {date}", { date: date(cur.since) })}</span>}
        </p>
        <ul className="mt-3 space-y-1.5 text-sm text-gray-200 leading-relaxed">
          {summary.map((line) => <li key={line}>{line}</li>)}
        </ul>
        {(() => {
          // The newest reading disagrees with the confirmed state: say so at
          // the top, not only in the sections, so the page never reads as
          // "healthy" above details that say otherwise.
          const next = data.latest && data.latest.regime !== cur.regime ? data.latest.regime : data.pending?.regime;
          if (!next || next === cur.regime) return null;
          const ns = REGIME_STYLE[next];
          return (
            <p className={`mt-3 text-sm font-medium rounded-lg border px-3 py-2 ${ns.cls} ${ns.text}`}>
              {ns.dot} {t("The latest reading points to: {r}. It becomes the market state, and an alert is sent, once it holds for two daily readings in a row (after the US close).",
                 "הקריאה האחרונה מצביעה על: {r}. זה יהפוך למצב השוק, ותישלח התראה, אם זה יחזיק בשתי קריאות יומיות ברצף (אחרי סגירת המסחר בארה״ב).",
                 { r: regimeLabel(t, next) })}
            </p>
          );
        })()}
        <p className="mt-3 text-[11px] text-gray-500 leading-relaxed">
          {t("This is risk information, not an instruction to sell. Whether to keep holding a stock depends on its stop loss.",
             "זהו מידע על רמת הסיכון ולא הוראה למכור. ההחלטה אם להמשיך להחזיק מניה תלויה בסטופ שלה.")}
          {" "}{t("Updated {date}", "עודכן {date}", { date: date(cur.as_of) })}.
        </p>
      </div>

      {/* 2. Your stocks — open, it is about the reader. */}
      <div className="bg-gray-900 rounded-2xl border border-gray-800 p-4">
        <p className="text-sm font-semibold text-gray-200">{t("Your stocks", "המניות שלך")}</p>
        {data.exposure.followed === 0 ? (
          <p className="text-xs text-gray-500 mt-2">
            {t("You are not following any stock yet.", "עדיין אינך עוקב אחרי אף מניה.")}{" "}
            <Link to="/recommendations" className="text-blue-400">{t("Go to Signals", "עבור לסיגנלים")}</Link>
          </p>
        ) : (
          <div className="mt-2 space-y-2 text-sm">
            <p className="text-gray-400 text-xs">
              {t("Near their stop loss (under 3%):", "קרובות לסטופ לוס (פחות מ-3%):")}{" "}
              {data.exposure.near_stop.length
                ? data.exposure.near_stop.map((x) => (
                    <span key={x.symbol} dir="ltr" className="inline-block text-orange-300 font-medium me-3">{x.symbol} ({x.gap_pct}%)</span>
                  ))
                : <span className="text-green-400">{t("none", "אין")}</span>}
            </p>
            <p className="text-gray-400 text-xs">
              {t("Highly volatile (usually hit harder in a fall):", "תנודתיות גבוהה (בדרך כלל נפגעות יותר בירידות):")}{" "}
              {data.exposure.volatile.length
                ? data.exposure.volatile.map((x) => (
                    <span key={x.symbol} dir="ltr" className="inline-block text-orange-300 font-medium me-3">{x.symbol} (β {x.beta})</span>
                  ))
                : <span className="text-green-400">{t("none", "אין")}</span>}
            </p>
          </div>
        )}
      </div>

      {/* 3. The detail, one tap away. */}
      <p className="text-xs text-gray-500 pt-1">{t("The details: tap a section to open it", "הפירוט: לחץ על חלק כדי לפתוח אותו")}</p>
      {layers.map((layer) => {
        const rows = data.indicators.filter((i) => i.layer === layer.key);
        if (!rows.length) return null;
        return (
          <Section key={layer.key} title={layer.title} sub={layer.sub} badge={<LayerBadge rows={rows} />}>
            <div className="divide-y divide-gray-800/70">
              {rows.map((ind) => {
                const info = indicatorInfo(t, ind.key);
                return (
                  <div key={ind.key} className="py-2.5">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm text-gray-200">{info.name}</span>
                      <span className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-white num" dir="ltr">{fmtValue(ind.key, ind.value)}</span>
                        <StatusPill status={ind.status} />
                      </span>
                    </div>
                    <p className="text-[11px] text-gray-500 mt-1">{info.why}</p>
                    <p className="text-[11px] text-gray-600 mt-0.5">{thresholdText(t, ind)}</p>
                  </div>
                );
              })}
            </div>
          </Section>
        );
      })}

      <Section title={t("Charts", "גרפים")} sub={t("S&P 500, VIX and credit spreads over the past year", "S&P 500, VIX ומרווחי אשראי בשנה האחרונה")}>
        <div className="space-y-3">
          <Chart
            locale={locale}
            title={t("S&P 500 and its averages, one year", "S&P 500 והממוצעים, שנה")}
            legend={
              <p className="text-[11px] text-gray-500">
                <span className="text-blue-400">━</span> S&P 500 (SPY) ·{" "}
                <span className="text-amber-400">━</span> {t("50-day", "50 יום")} ·{" "}
                <span className="text-red-400">━</span> {t("200-day", "200 יום")}
              </p>
            }
            data={s.spy.map(([d, v, a, b]) => ({ d, v, a, b }))}
          />
          <Chart
            locale={locale}
            title={t("VIX, one year", "VIX, שנה")}
            legend={<p className="text-[11px] text-gray-500">{t("Dashed lines: warning at 25, alarm at 35", "קווים מקווקווים: אזהרה ב-25, אזעקה ב-35")}</p>}
            refs={[{ y: 25, color: "#ca8a04" }, { y: 35, color: "#dc2626" }]}
            data={s.vix.map(([d, v]) => ({ d, v }))}
          />
          <Chart
            locale={locale}
            title={t("High-yield credit spread, one year", "מרווח אשראי בתשואה גבוהה, שנה")}
            legend={<p className="text-[11px] text-gray-500">{t("Dashed lines: warning at 5%, alarm at 7%", "קווים מקווקווים: אזהרה ב-5%, אזעקה ב-7%")}</p>}
            refs={[{ y: 5, color: "#ca8a04" }, { y: 7, color: "#dc2626" }]}
            data={s.hy_spread.map(([d, v]) => ({ d, v }))}
          />
        </div>
      </Section>

      <Section
        title={t("Changes of market state", "שינויים במצב השוק")}
        sub={t("And what the S&P 500 did next", "ומה עשה S&P 500 אחר כך")}
        badge={<span className="text-[11px] text-gray-500">{data.history.length}</span>}
      >
        <p className="text-[11px] text-gray-500">
          {t("And what the S&P 500 did next: the plainest test of whether this reading sees anything.",
             "ומה עשה S&P 500 אחר כך: המבחן הפשוט ביותר אם הקריאה הזו באמת מזהה משהו.")}
        </p>
        {data.history.length === 0 ? (
          <p className="text-xs text-gray-500 mt-3">{t("No change since tracking began.", "לא היה שינוי מאז שהמעקב התחיל.")}</p>
        ) : (
          <div className="mt-2 divide-y divide-gray-800/70">
            {data.history.map((h) => (
              <div key={h.at} className="py-2.5 text-sm">
                <p className="text-gray-200">
                  {date(h.at)}: {t("was {from}, now {to}", "היה {from}, עכשיו {to}",
                    { from: regimeLabel(t, h.from), to: regimeLabel(t, h.to) })}
                </p>
                <p className="text-[11px] text-gray-500 mt-0.5">
                  {t("S&P 500 a week later: {w} · a month later: {m}", "S&P 500 אחרי שבוע: {w} · אחרי חודש: {m}",
                    { w: pct(h.spy_1w_pct), m: pct(h.spy_1m_pct) })}
                </p>
              </div>
            ))}
          </div>
        )}
      </Section>

      <p className="text-[11px] text-gray-600 leading-relaxed pb-2">
        {t("Sources: prices of the S&P 500 and of regional index funds, and VIX, credit spreads, stress indices, the yield curve, the dollar and the yen from the Federal Reserve's FRED database. Updated after each US trading day.",
           "מקורות: מחירי S&P 500 וקרנות סל אזוריות, ו-VIX, מרווחי אשראי, מדדי לחץ, עקום התשואות, הדולר והין ממאגר FRED של הבנק הפדרלי. מתעדכן אחרי כל יום מסחר בארה״ב.")}
      </p>
    </div>
  );
};

export default MarketPage;
