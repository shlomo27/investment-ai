import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../store";
import { completeOnboarding } from "../store/slices/authSlice";
import { RiskProfile } from "../types";

type RiskLevel = "CONSERVATIVE" | "HYBRID" | "AGGRESSIVE";
type InvestmentType = "STOCKS" | "ETFS" | "BOTH";

interface PortfolioHolding {
  symbol: string;
  quantity: string;
  avg_price: string;
}

const STEPS = ["welcome", "risk", "assets", "portfolio", "confirm"];

const Onboarding: React.FC = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const { user, isLoading, error } = useAppSelector((state) => state.auth);
  const isHe = (user?.preferred_language || "he") === "he";

  const [step, setStep] = useState(0);

  // Step 1 — Risk
  const [riskLevel, setRiskLevel] = useState<RiskLevel | null>(null);
  const [allowsVolatile, setAllowsVolatile] = useState(false);
  const [allowsLeveraged, setAllowsLeveraged] = useState(false);
  const [allowsShort, setAllowsShort] = useState(false);

  // Step 2 — Asset type
  const [investmentType, setInvestmentType] = useState<InvestmentType | null>(null);

  // Step 3 — Existing portfolio
  const [hasPortfolio, setHasPortfolio] = useState<boolean | null>(null);
  const [holdings, setHoldings] = useState<PortfolioHolding[]>([
    { symbol: "", quantity: "", avg_price: "" },
  ]);

  // Step 4 — Notifications
  const [notifications, setNotifications] = useState({
    email: true,
    sms: true,
    push: false,
  });

  const riskScoreMap: Record<RiskLevel, number> = {
    CONSERVATIVE: 25,
    HYBRID: 55,
    AGGRESSIVE: 85,
  };

  const profileMap: Record<RiskLevel, RiskProfile> = {
    CONSERVATIVE: RiskProfile.CONSERVATIVE,
    HYBRID: RiskProfile.HYBRID,
    AGGRESSIVE: RiskProfile.AGGRESSIVE,
  };

  const addHolding = () =>
    setHoldings([...holdings, { symbol: "", quantity: "", avg_price: "" }]);

  const updateHolding = (i: number, field: keyof PortfolioHolding, value: string) => {
    const updated = [...holdings];
    updated[i] = { ...updated[i], [field]: value };
    setHoldings(updated);
  };

  const removeHolding = (i: number) =>
    setHoldings(holdings.filter((_, idx) => idx !== i));

  const validHoldings = holdings.filter((h) => h.symbol.trim() && h.quantity);

  const handleComplete = async () => {
    if (!riskLevel || !investmentType) return;
    const result = await dispatch(
      completeOnboarding({
        risk_profile: profileMap[riskLevel],
        risk_score: riskScoreMap[riskLevel],
        investment_type: investmentType,
        allows_volatile: allowsVolatile,
        allows_leveraged: allowsLeveraged,
        allows_short: allowsShort,
        notification_email: notifications.email,
        notification_sms: notifications.sms,
        notification_push: notifications.push,
      })
    );
    if (completeOnboarding.fulfilled.match(result)) {
      navigate("/dashboard");
    }
  };

  const riskCards: { level: RiskLevel; icon: string; color: string; borderColor: string; he: string; en: string; desc_he: string; desc_en: string }[] = [
    {
      level: "CONSERVATIVE",
      icon: "🟢",
      color: "text-green-400",
      borderColor: "border-green-500",
      he: "שמרני",
      en: "Conservative",
      desc_he: "S&P 500, ETF דיבידנדים, מניות יציבות. סיכון נמוך, תשואה עקבית.",
      desc_en: "S&P 500, dividend ETFs, stable stocks. Low risk, consistent returns.",
    },
    {
      level: "HYBRID",
      icon: "🟡",
      color: "text-yellow-400",
      borderColor: "border-yellow-500",
      he: "סיכון בינוני",
      en: "Medium Risk",
      desc_he: "שילוב מניות צמיחה ו-ETF. פוטנציאל תשואה גבוה יותר עם סיכון מתון.",
      desc_en: "Growth stocks and ETF mix. Higher return potential with moderate risk.",
    },
    {
      level: "AGGRESSIVE",
      icon: "🔴",
      color: "text-red-400",
      borderColor: "border-red-500",
      he: "סיכון גבוה",
      en: "High Risk",
      desc_he: "מניות תנודתיות, מינוף, שורט. מחיר יכול לרדת עשרות אחוזים ביום.",
      desc_en: "Volatile stocks, leverage, short. Price can drop tens of percent in a day.",
    },
  ];

  const assetCards: { type: InvestmentType; icon: string; he: string; en: string; desc_he: string; desc_en: string }[] = [
    {
      type: "STOCKS",
      icon: "📈",
      he: "מניות בלבד",
      en: "Stocks Only",
      desc_he: "מניות ספציפיות בשוק",
      desc_en: "Individual company stocks",
    },
    {
      type: "ETFS",
      icon: "🗂️",
      he: "ETF בלבד",
      en: "ETFs Only",
      desc_he: "קרנות מדד מגוונות",
      desc_en: "Diversified index funds",
    },
    {
      type: "BOTH",
      icon: "🔀",
      he: "שניהם",
      en: "Both",
      desc_he: "מניות וETF — מגוון מלא",
      desc_en: "Stocks and ETFs — full variety",
    },
  ];

  return (
    <div
      className="min-h-screen bg-gray-950 text-gray-100 flex items-center justify-center px-4 py-8"
      dir={isHe ? "rtl" : "ltr"}
    >
      <div className="w-full max-w-2xl">
        {/* Progress bar */}
        <div className="mb-8">
          <div className="flex gap-2 mb-3">
            {STEPS.map((_, i) => (
              <div
                key={i}
                className={`h-1 flex-1 rounded-full transition-colors ${i <= step ? "bg-blue-500" : "bg-gray-700"}`}
              />
            ))}
          </div>
          <p className="text-sm text-gray-400">
            {isHe ? `שלב ${step + 1} מתוך ${STEPS.length}` : `Step ${step + 1} of ${STEPS.length}`}
          </p>
        </div>

        {/* ── Step 0: Welcome ─────────────────────────────────────── */}
        {step === 0 && (
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h2 className="text-2xl font-bold mb-2">
              {isHe ? `שלום, ${user?.full_name}!` : `Hello, ${user?.full_name}!`}
            </h2>
            <p className="text-gray-400 mb-6">
              {isHe
                ? "ברוכים הבאים למערכת ה-AI. נגדיר יחד את פרופיל ההשקעה שלך."
                : "Welcome to the AI platform. Let's set up your investment profile together."}
            </p>
            <div className="grid grid-cols-2 gap-4 mb-6">
              {[
                { he: "ניתוח AI מתקדם", en: "Advanced AI Analysis", icon: "🤖" },
                { he: "ניהול סיכונים", en: "Risk Management", icon: "🛡️" },
                { he: "התראות בזמן אמת", en: "Real-Time Alerts", icon: "🔔" },
                { he: "שווקים גלובליים", en: "Global Markets", icon: "🌍" },
              ].map((f) => (
                <div key={f.en} className="bg-gray-800 rounded-xl p-4">
                  <span className="text-2xl">{f.icon}</span>
                  <p className="text-sm mt-2 font-medium">{isHe ? f.he : f.en}</p>
                </div>
              ))}
            </div>
            <button
              onClick={() => setStep(1)}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white rounded-xl py-3 font-medium"
            >
              {isHe ? "בואו נתחיל" : "Let's Begin"}
            </button>
          </div>
        )}

        {/* ── Step 1: Risk Level ───────────────────────────────────── */}
        {step === 1 && (
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h2 className="text-xl font-bold mb-1">
              {isHe ? "מהי רמת הסיכון שאתה מוכן לקחת?" : "What risk level are you willing to take?"}
            </h2>
            <p className="text-gray-400 text-sm mb-6">
              {isHe ? "זה קובע אילו מניות ו-ETF המערכת תמליץ עליך" : "This determines which stocks and ETFs the system recommends for you"}
            </p>

            <div className="space-y-3 mb-6">
              {riskCards.map((card) => (
                <button
                  key={card.level}
                  onClick={() => {
                    setRiskLevel(card.level);
                    if (card.level !== "AGGRESSIVE") {
                      setAllowsVolatile(false);
                      setAllowsLeveraged(false);
                      setAllowsShort(false);
                    }
                  }}
                  className={`w-full text-right p-4 rounded-xl border-2 transition-all ${
                    riskLevel === card.level
                      ? `${card.borderColor} bg-gray-800`
                      : "border-gray-700 hover:border-gray-600"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{card.icon}</span>
                    <div className="flex-1 text-start">
                      <p className={`font-bold ${riskLevel === card.level ? card.color : "text-white"}`}>
                        {isHe ? card.he : card.en}
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        {isHe ? card.desc_he : card.desc_en}
                      </p>
                    </div>
                    {riskLevel === card.level && (
                      <span className={`text-xl ${card.color}`}>✓</span>
                    )}
                  </div>
                </button>
              ))}
            </div>

            {/* High-risk sub-options */}
            {riskLevel === "AGGRESSIVE" && (
              <div className="bg-red-950/30 border border-red-800/50 rounded-xl p-4 mb-6">
                <p className="text-sm font-medium text-red-300 mb-3">
                  {isHe ? "אפשרויות סיכון גבוה נוספות:" : "Additional high-risk options:"}
                </p>
                {[
                  {
                    key: "volatile" as const,
                    val: allowsVolatile,
                    set: setAllowsVolatile,
                    he: "מניות עם תנודתיות גבוהה מאוד",
                    en: "Very high-volatility stocks",
                    sub_he: "מחיר יכול לרדת 30-70% ביום, פוטנציאל לחדלות פירעון",
                    sub_en: "Price can drop 30-70% in a day, bankruptcy risk",
                  },
                  {
                    key: "leveraged" as const,
                    val: allowsLeveraged,
                    set: setAllowsLeveraged,
                    he: "ETF ממונף ×2 / ×3",
                    en: "Leveraged ETF ×2 / ×3",
                    sub_he: "תנועת מדד מוכפלת פי 2 או 3 — בשני הכיוונים",
                    sub_en: "Index movement multiplied 2x or 3x — in both directions",
                  },
                  {
                    key: "short" as const,
                    val: allowsShort,
                    set: setAllowsShort,
                    he: "ETF SHORT (מינוף הפוך)",
                    en: "Short ETF (inverse leverage)",
                    sub_he: "מרוויח כאשר השוק יורד",
                    sub_en: "Profits when the market falls",
                  },
                ].map((opt) => (
                  <button
                    key={opt.key}
                    onClick={() => opt.set(!opt.val)}
                    className={`w-full flex items-start gap-3 p-3 rounded-lg mb-2 text-start transition-colors ${
                      opt.val ? "bg-red-900/40 border border-red-700/50" : "hover:bg-gray-800"
                    }`}
                  >
                    <div className={`w-5 h-5 mt-0.5 rounded border-2 flex-shrink-0 flex items-center justify-center ${
                      opt.val ? "bg-red-600 border-red-600" : "border-gray-600"
                    }`}>
                      {opt.val && <span className="text-white text-xs">✓</span>}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-red-200">{isHe ? opt.he : opt.en}</p>
                      <p className="text-xs text-gray-500 mt-0.5">{isHe ? opt.sub_he : opt.sub_en}</p>
                    </div>
                  </button>
                ))}
                <p className="text-xs text-red-400/70 mt-2">
                  {isHe
                    ? "⚠️ ההמלצות לנכסים אלו יכללו אזהרת סיכון מפורשת"
                    : "⚠️ Recommendations for these assets will include explicit risk warnings"}
                </p>
              </div>
            )}

            <div className="flex gap-3">
              <button onClick={() => setStep(0)} className="flex-1 border border-gray-700 rounded-xl py-3 text-gray-400">
                {isHe ? "חזרה" : "Back"}
              </button>
              <button
                onClick={() => setStep(2)}
                disabled={!riskLevel}
                className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-xl py-3 font-medium"
              >
                {isHe ? "המשך" : "Continue"}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 2: Asset Type ───────────────────────────────────── */}
        {step === 2 && (
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h2 className="text-xl font-bold mb-1">
              {isHe ? "איזה סוג נכסים אתה מעוניין?" : "Which type of assets interest you?"}
            </h2>
            <p className="text-gray-400 text-sm mb-6">
              {isHe
                ? "המערכת תסנן המלצות לפי ההעדפה שלך"
                : "The system will filter recommendations based on your preference"}
            </p>

            <div className="space-y-3 mb-6">
              {assetCards.map((card) => (
                <button
                  key={card.type}
                  onClick={() => setInvestmentType(card.type)}
                  className={`w-full p-4 rounded-xl border-2 transition-all ${
                    investmentType === card.type
                      ? "border-blue-500 bg-blue-500/10"
                      : "border-gray-700 hover:border-gray-600"
                  }`}
                >
                  <div className="flex items-center gap-4">
                    <span className="text-3xl">{card.icon}</span>
                    <div className="flex-1 text-start">
                      <p className={`font-bold ${investmentType === card.type ? "text-blue-300" : "text-white"}`}>
                        {isHe ? card.he : card.en}
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        {isHe ? card.desc_he : card.desc_en}
                      </p>
                    </div>
                    {investmentType === card.type && (
                      <span className="text-blue-400 text-xl">✓</span>
                    )}
                  </div>
                </button>
              ))}
            </div>

            <div className="flex gap-3">
              <button onClick={() => setStep(1)} className="flex-1 border border-gray-700 rounded-xl py-3 text-gray-400">
                {isHe ? "חזרה" : "Back"}
              </button>
              <button
                onClick={() => setStep(3)}
                disabled={!investmentType}
                className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-xl py-3 font-medium"
              >
                {isHe ? "המשך" : "Continue"}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 3: Existing Portfolio ───────────────────────────── */}
        {step === 3 && (
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h2 className="text-xl font-bold mb-1">
              {isHe ? "האם יש לך תיק השקעות קיים?" : "Do you have an existing portfolio?"}
            </h2>
            <p className="text-gray-400 text-sm mb-6">
              {isHe
                ? "אם כן, המערכת תנתח אותו ותבדוק התאמה לפרופיל הסיכון שלך"
                : "If yes, the system will analyze it and check alignment with your risk profile"}
            </p>

            <div className="flex gap-3 mb-6">
              <button
                onClick={() => setHasPortfolio(false)}
                className={`flex-1 py-4 rounded-xl border-2 font-medium transition-all ${
                  hasPortfolio === false
                    ? "border-blue-500 bg-blue-500/10 text-blue-300"
                    : "border-gray-700 text-gray-400 hover:border-gray-600"
                }`}
              >
                {isHe ? "לא, אני מתחיל מאפס" : "No, starting fresh"}
              </button>
              <button
                onClick={() => setHasPortfolio(true)}
                className={`flex-1 py-4 rounded-xl border-2 font-medium transition-all ${
                  hasPortfolio === true
                    ? "border-blue-500 bg-blue-500/10 text-blue-300"
                    : "border-gray-700 text-gray-400 hover:border-gray-600"
                }`}
              >
                {isHe ? "כן, יש לי תיק" : "Yes, I have a portfolio"}
              </button>
            </div>

            {hasPortfolio === true && (
              <div className="mb-6">
                <p className="text-sm text-gray-400 mb-3">
                  {isHe ? "הכנס את האחזקות הקיימות שלך:" : "Enter your current holdings:"}
                </p>

                <div className="space-y-2">
                  {/* Header row */}
                  <div className={`grid grid-cols-12 gap-2 text-xs text-gray-500 px-1`}>
                    <span className="col-span-4">{isHe ? "סמל מניה" : "Symbol"}</span>
                    <span className="col-span-3">{isHe ? "כמות" : "Quantity"}</span>
                    <span className="col-span-4">{isHe ? "מחיר קנייה" : "Avg Buy Price"}</span>
                    <span className="col-span-1" />
                  </div>

                  {holdings.map((h, i) => (
                    <div key={i} className="grid grid-cols-12 gap-2">
                      <input
                        value={h.symbol}
                        onChange={(e) => updateHolding(i, "symbol", e.target.value.toUpperCase())}
                        placeholder="AAPL"
                        className="col-span-4 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 uppercase"
                      />
                      <input
                        value={h.quantity}
                        onChange={(e) => updateHolding(i, "quantity", e.target.value)}
                        placeholder="10"
                        type="number"
                        min="0"
                        className="col-span-3 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                      />
                      <input
                        value={h.avg_price}
                        onChange={(e) => updateHolding(i, "avg_price", e.target.value)}
                        placeholder="$180"
                        className="col-span-4 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                      />
                      <button
                        onClick={() => removeHolding(i)}
                        disabled={holdings.length === 1}
                        className="col-span-1 text-gray-600 hover:text-red-400 disabled:opacity-20 text-lg"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>

                <button
                  onClick={addHolding}
                  className="mt-3 text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1"
                >
                  <span className="text-lg">+</span>
                  {isHe ? "הוסף אחזקה" : "Add holding"}
                </button>

                {validHoldings.length > 0 && (
                  <div className="mt-4 p-3 bg-blue-950/30 border border-blue-800/40 rounded-xl text-sm text-blue-300">
                    {isHe
                      ? `✓ ${validHoldings.length} אחזקות יוזנו לניתוח ראשוני לאחר ההרשמה`
                      : `✓ ${validHoldings.length} holdings will be analyzed after setup`}
                  </div>
                )}
              </div>
            )}

            {hasPortfolio === false && (
              <div className="mb-6 p-4 bg-gray-800 rounded-xl text-sm text-gray-400">
                {isHe
                  ? "המערכת תבנה עבורך רשימת המלצות בהתאם לפרופיל הסיכון שבחרת."
                  : "The system will build a recommendation list tailored to your chosen risk profile."}
              </div>
            )}

            <div className="flex gap-3">
              <button onClick={() => setStep(2)} className="flex-1 border border-gray-700 rounded-xl py-3 text-gray-400">
                {isHe ? "חזרה" : "Back"}
              </button>
              <button
                onClick={() => setStep(4)}
                disabled={hasPortfolio === null}
                className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-xl py-3 font-medium"
              >
                {isHe ? "המשך" : "Continue"}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 4: Confirm ──────────────────────────────────────── */}
        {step === 4 && riskLevel && investmentType && (
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h2 className="text-xl font-bold mb-4">
              {isHe ? "אישור פרופיל" : "Confirm Profile"}
            </h2>

            {/* Summary rows */}
            <div className="space-y-3 mb-6">
              {[
                {
                  label: isHe ? "רמת סיכון" : "Risk Level",
                  value: riskCards.find((c) => c.level === riskLevel)!,
                  render: (v: typeof riskCards[0]) => (
                    <span className={`font-bold ${v.color}`}>{isHe ? v.he : v.en}</span>
                  ),
                },
                {
                  label: isHe ? "סוג נכסים" : "Asset Type",
                  value: assetCards.find((c) => c.type === investmentType)!,
                  render: (v: typeof assetCards[0]) => (
                    <span className="font-bold text-white">{v.icon} {isHe ? v.he : v.en}</span>
                  ),
                },
              ].map(({ label, value, render }) => (
                <div key={label} className="flex justify-between items-center py-3 border-b border-gray-800">
                  <span className="text-gray-400 text-sm">{label}</span>
                  {render(value as any)}
                </div>
              ))}

              {riskLevel === "AGGRESSIVE" && (allowsVolatile || allowsLeveraged || allowsShort) && (
                <div className="flex justify-between items-center py-3 border-b border-gray-800">
                  <span className="text-gray-400 text-sm">{isHe ? "אפשרויות מתקדמות" : "Advanced Options"}</span>
                  <div className="flex gap-1 flex-wrap justify-end">
                    {allowsVolatile && <span className="px-2 py-0.5 bg-red-900/50 text-red-300 rounded text-xs">{isHe ? "תנודתיות גבוהה" : "High Vol"}</span>}
                    {allowsLeveraged && <span className="px-2 py-0.5 bg-red-900/50 text-red-300 rounded text-xs">{isHe ? "ממונף ×2/3" : "Leveraged"}</span>}
                    {allowsShort && <span className="px-2 py-0.5 bg-red-900/50 text-red-300 rounded text-xs">Short</span>}
                  </div>
                </div>
              )}

              {hasPortfolio && validHoldings.length > 0 && (
                <div className="flex justify-between items-center py-3 border-b border-gray-800">
                  <span className="text-gray-400 text-sm">{isHe ? "תיק קיים" : "Existing Portfolio"}</span>
                  <span className="font-bold text-green-400">{validHoldings.length} {isHe ? "אחזקות" : "holdings"}</span>
                </div>
              )}
            </div>

            {/* Notifications */}
            <div className="bg-gray-800 rounded-xl p-4 mb-6">
              <p className="text-sm text-gray-400 mb-3">{isHe ? "ערוצי התראה" : "Notification Channels"}</p>
              {[
                { key: "email", he: "דוא\"ל", en: "Email" },
                { key: "sms", he: "SMS", en: "SMS" },
                { key: "push", he: "Push", en: "Push" },
              ].map((ch) => (
                <div key={ch.key} className="flex items-center justify-between py-2">
                  <span className="text-sm">{isHe ? ch.he : ch.en}</span>
                  <button
                    onClick={() => setNotifications({ ...notifications, [ch.key]: !notifications[ch.key as keyof typeof notifications] })}
                    className={`w-10 h-5 rounded-full transition-colors relative ${
                      notifications[ch.key as keyof typeof notifications] ? "bg-blue-600" : "bg-gray-600"
                    }`}
                  >
                    <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all ${
                      notifications[ch.key as keyof typeof notifications] ? (isHe ? "right-0.5" : "left-5") : (isHe ? "right-5" : "left-0.5")
                    }`} />
                  </button>
                </div>
              ))}
            </div>

            {error && (
              <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 mb-4 text-red-300 text-sm">
                {error}
              </div>
            )}

            <div className="flex gap-3">
              <button onClick={() => setStep(3)} className="flex-1 border border-gray-700 rounded-xl py-3 text-gray-400">
                {isHe ? "חזרה" : "Back"}
              </button>
              <button
                onClick={handleComplete}
                disabled={isLoading}
                className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white rounded-xl py-3 font-medium"
              >
                {isLoading ? (isHe ? "שומר..." : "Saving...") : (isHe ? "אישור והתחלה" : "Confirm & Start")}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Onboarding;
