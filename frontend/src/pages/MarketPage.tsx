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
import { reasonText } from "../components/Market/MarketRegimeCard";

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
    default: return { name: key, why: "" };
  }
}

function fmtValue(key: string, v: number | null): string {
  if (v === null || v === undefined) return "—";
  if (key === "spy_vs_200" || key === "spy_vs_50") return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
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
  const top = [...cur.reasons].sort((a, b) => b.points - a.points).slice(0, 4);
  const date = (iso?: string | null) => (iso ? new Date(iso).toLocaleDateString(locale, { day: "numeric", month: "long", year: "numeric" }) : "");
  const layers: { key: "trend" | "stress" | "breadth"; title: string; sub: string }[] = [
    { key: "trend", title: t("Trend", "מגמה"), sub: t("Where the index is heading", "לאן המדד הולך") },
    { key: "stress", title: t("Crisis detectors", "גלאי משבר"), sub: t("The measures that moved before the index in past crises", "המדדים שזזו לפני המדד במשברים קודמים") },
    { key: "breadth", title: t("Breadth", "רוחב השוק"), sub: t("How many stocks share the move", "כמה מניות שותפות לתנועה") },
  ];
  // Isolated left-to-right, so a minus sign stays in front of the number
  // inside a right-to-left sentence.
  const pct = (v: number | null) => (v === null ? "—" : `\u2066${v > 0 ? "+" : ""}${v.toFixed(1)}%\u2069`);
  const s = data.series;

  return (
    <div dir={dir} className="space-y-5">
      <h1 className="text-2xl font-bold">{t("Market", "שוק")}</h1>

      {/* 1. Where the market stands */}
      <div className={`rounded-2xl border p-4 ${style.cls}`}>
        <p className={`text-lg font-bold ${style.text}`}>{style.dot} {regimeLabel(t, cur.regime)}</p>
        <p className="text-xs text-gray-400 mt-1">
          {cur.since ? t("Since {date}", "מאז {date}", { date: date(cur.since) }) : ""}
          {" · "}{t("Score {s}", "ציון {s}", { s: cur.score })}
          {" · "}{t("Updated {date}", "עודכן {date}", { date: date(cur.as_of) })}
        </p>
        {top.length > 0 ? (
          <ul className="mt-3 space-y-1 text-sm text-gray-200">
            {top.map((r) => <li key={r.code || r.en}>• {reasonText(t, r)}</li>)}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-gray-300">
            {t("Trend, credit and stress measures are all within normal ranges.", "מדדי המגמה, האשראי והלחץ כולם בטווח הרגיל.")}
          </p>
        )}
        {data.pending && data.pending.regime !== cur.regime && (
          <p className="mt-3 text-xs text-gray-400">
            {t("Latest reading points to: {r}. It becomes the new state if the next reading confirms it.",
               "הקריאה האחרונה מצביעה על: {r}. זה יהפוך למצב החדש אם הקריאה הבאה תאשר.",
               { r: regimeLabel(t, data.pending.regime) })}
          </p>
        )}
        <p className="mt-3 text-[11px] text-gray-500 leading-relaxed">
          {t("This is risk information, not an instruction to sell. Whether to keep holding a stock depends on its stop loss.",
             "זהו מידע על רמת הסיכון ולא הוראה למכור. ההחלטה אם להמשיך להחזיק מניה תלויה בסטופ שלה.")}
        </p>
      </div>

      {/* 2. Your stocks */}
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
                    <span key={x.symbol} className="text-orange-300 font-medium me-2">{x.symbol} <span className="num" dir="ltr">({x.gap_pct}%)</span></span>
                  ))
                : <span className="text-green-400">{t("none", "אין")}</span>}
            </p>
            <p className="text-gray-400 text-xs">
              {t("Highly volatile (usually hit harder in a fall):", "תנודתיות גבוהה (בדרך כלל נפגעות יותר בירידות):")}{" "}
              {data.exposure.volatile.length
                ? data.exposure.volatile.map((x) => (
                    <span key={x.symbol} className="text-orange-300 font-medium me-2">{x.symbol} <span className="num" dir="ltr">(β {x.beta})</span></span>
                  ))
                : <span className="text-green-400">{t("none", "אין")}</span>}
            </p>
          </div>
        )}
      </div>

      {/* 3. What was checked */}
      {layers.map((layer) => {
        const rows = data.indicators.filter((i) => i.layer === layer.key);
        if (!rows.length) return null;
        return (
          <div key={layer.key} className="bg-gray-900 rounded-2xl border border-gray-800 p-4">
            <p className="text-sm font-semibold text-gray-200">{layer.title}</p>
            <p className="text-[11px] text-gray-500">{layer.sub}</p>
            <div className="mt-2 divide-y divide-gray-800/70">
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
          </div>
        );
      })}

      {/* 4. A year of history */}
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

      {/* 5. Past changes, and what the index did next */}
      <div className="bg-gray-900 rounded-2xl border border-gray-800 p-4">
        <p className="text-sm font-semibold text-gray-200">{t("Changes of market state", "שינויים במצב השוק")}</p>
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
      </div>

      <p className="text-[11px] text-gray-600 leading-relaxed pb-2">
        {t("Sources: S&P 500 prices, and VIX, credit spreads, stress indices and the yield curve from the Federal Reserve's FRED database. Updated after each US trading day.",
           "מקורות: מחירי S&P 500, ו-VIX, מרווחי אשראי, מדדי לחץ ועקום התשואות ממאגר FRED של הבנק הפדרלי. מתעדכן אחרי כל יום מסחר בארה״ב.")}
      </p>
    </div>
  );
};

export default MarketPage;
