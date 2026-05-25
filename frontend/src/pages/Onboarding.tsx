import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../store";
import { completeOnboarding } from "../store/slices/authSlice";
import { RiskProfile, RiskQuestion } from "../types";
import { marketApi } from "../api/client";

const RISK_QUESTIONS: RiskQuestion[] = [
  {
    id: "q1",
    question_he: "מהי מטרת ההשקעה שלך?",
    question_en: "What is your primary investment goal?",
    options: [
      { value: 20, label_he: "שמירת הון", label_en: "Capital preservation" },
      { value: 40, label_he: "הכנסה סדירה", label_en: "Regular income" },
      { value: 60, label_he: "צמיחה מאוזנת", label_en: "Balanced growth" },
      { value: 80, label_he: "צמיחה מהירה", label_en: "Aggressive growth" },
    ],
    weight: 1.5,
  },
  {
    id: "q2",
    question_he: "מהו אופק ההשקעה שלך?",
    question_en: "What is your investment time horizon?",
    options: [
      { value: 20, label_he: "פחות משנה", label_en: "Less than 1 year" },
      { value: 40, label_he: "1-3 שנים", label_en: "1-3 years" },
      { value: 60, label_he: "3-7 שנים", label_en: "3-7 years" },
      { value: 80, label_he: "יותר מ-7 שנים", label_en: "More than 7 years" },
    ],
    weight: 1.0,
  },
  {
    id: "q3",
    question_he: "כיצד תגיב לירידה של 20% בתיק תוך חודש?",
    question_en: "How would you react to a 20% portfolio drop in one month?",
    options: [
      { value: 10, label_he: "אמכור הכל מיד", label_en: "Sell everything immediately" },
      { value: 30, label_he: "אמכור חלק", label_en: "Sell some positions" },
      { value: 60, label_he: "אחכה ואראה", label_en: "Wait and see" },
      { value: 90, label_he: "אקנה עוד", label_en: "Buy more (opportunity)" },
    ],
    weight: 1.5,
  },
  {
    id: "q4",
    question_he: "מה אחוז החסכונות שאתה מוכן להשקיע?",
    question_en: "What percentage of savings are you willing to invest?",
    options: [
      { value: 20, label_he: "עד 10%", label_en: "Up to 10%" },
      { value: 40, label_he: "10%-25%", label_en: "10%-25%" },
      { value: 60, label_he: "25%-50%", label_en: "25%-50%" },
      { value: 80, label_he: "יותר מ-50%", label_en: "More than 50%" },
    ],
    weight: 1.0,
  },
  {
    id: "q5",
    question_he: "כמה ניסיון השקעות יש לך?",
    question_en: "How much investment experience do you have?",
    options: [
      { value: 20, label_he: "ללא ניסיון", label_en: "No experience" },
      { value: 40, label_he: "ניסיון מועט", label_en: "Limited experience" },
      { value: 60, label_he: "ניסיון בינוני", label_en: "Moderate experience" },
      { value: 80, label_he: "ניסיון רב", label_en: "Extensive experience" },
    ],
    weight: 0.8,
  },
];

function calculateRiskProfile(score: number): RiskProfile {
  if (score < 30) return RiskProfile.CONSERVATIVE;
  if (score < 50) return RiskProfile.PASSIVE;
  if (score < 70) return RiskProfile.HYBRID;
  return RiskProfile.AGGRESSIVE;
}

const STEPS = ["account", "risk", "deposit", "confirm"];

const Onboarding: React.FC = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const { user, isLoading, error } = useAppSelector((state) => state.auth);
  const lang = user?.preferred_language || "he";
  const isHe = lang === "he";

  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [deposit, setDeposit] = useState<number>(10000);
  const [notifications, setNotifications] = useState({
    email: true,
    sms: true,
    push: false,
  });
  const [poolAssets, setPoolAssets] = useState<any[]>([]);

  const totalWeight = RISK_QUESTIONS.reduce((s, q) => s + q.weight, 0);
  const answeredCount = Object.keys(answers).length;
  const allAnswered = answeredCount === RISK_QUESTIONS.length;

  const riskScore = allAnswered
    ? Math.round(
        RISK_QUESTIONS.reduce((sum, q) => {
          const ans = answers[q.id] || 50;
          return sum + (ans * q.weight) / totalWeight;
        }, 0)
      )
    : 50;

  const riskProfile = calculateRiskProfile(riskScore);

  useEffect(() => {
    if (step === 3) {
      marketApi.getAssetPool({ activeOnly: true }).then(setPoolAssets).catch(() => {});
    }
  }, [step]);

  const handleComplete = async () => {
    const result = await dispatch(
      completeOnboarding({
        risk_profile: riskProfile,
        risk_score: riskScore,
        initial_deposit: deposit,
        notification_email: notifications.email,
        notification_sms: notifications.sms,
        notification_push: notifications.push,
      })
    );
    if (completeOnboarding.fulfilled.match(result)) {
      navigate("/dashboard");
    }
  };

  const profileLabels: Record<RiskProfile, { he: string; en: string; color: string }> = {
    [RiskProfile.CONSERVATIVE]: { he: "שמרני", en: "Conservative", color: "text-green-400" },
    [RiskProfile.PASSIVE]: { he: "פסיבי", en: "Passive", color: "text-blue-400" },
    [RiskProfile.HYBRID]: { he: "היברידי", en: "Hybrid", color: "text-yellow-400" },
    [RiskProfile.AGGRESSIVE]: { he: "אגרסיבי", en: "Aggressive", color: "text-red-400" },
  };

  return (
    <div
      className="min-h-screen bg-gray-950 text-gray-100 flex items-center justify-center px-4"
      dir={isHe ? "rtl" : "ltr"}
    >
      <div className="w-full max-w-2xl">
        {/* Progress */}
        <div className="mb-8">
          <div className="flex gap-2 mb-3">
            {STEPS.map((s, i) => (
              <div
                key={s}
                className={`h-1 flex-1 rounded-full ${i <= step ? "bg-blue-500" : "bg-gray-700"}`}
              />
            ))}
          </div>
          <p className="text-sm text-gray-400">
            {isHe ? `שלב ${step + 1} מתוך ${STEPS.length}` : `Step ${step + 1} of ${STEPS.length}`}
          </p>
        </div>

        {/* Step 0: Welcome */}
        {step === 0 && (
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h2 className="text-2xl font-bold mb-2">
              {isHe ? `שלום, ${user?.full_name}!` : `Hello, ${user?.full_name}!`}
            </h2>
            <p className="text-gray-400 mb-6">
              {isHe
                ? "ברוכים הבאים לפלטפורמת ההשקעות החכמה. בשלבים הבאים נלמד על פרופיל הסיכון שלך."
                : "Welcome to the intelligent investment platform. In the next steps, we'll learn about your risk profile."}
            </p>
            <div className="grid grid-cols-2 gap-4 mb-6">
              {[
                { he: "ניתוח AI מתקדם", en: "Advanced AI Analysis", icon: "🤖" },
                { he: "ניהול סיכונים", en: "Risk Management", icon: "🛡️" },
                { he: "שווקים גלובליים", en: "Global Markets", icon: "🌍" },
                { he: "התראות חכמות", en: "Smart Alerts", icon: "🔔" },
              ].map((feat) => (
                <div key={feat.en} className="bg-gray-800 rounded-xl p-4">
                  <span className="text-2xl">{feat.icon}</span>
                  <p className="text-sm mt-2 font-medium">{isHe ? feat.he : feat.en}</p>
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

        {/* Step 1: Risk Questionnaire */}
        {step === 1 && (
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h2 className="text-xl font-bold mb-1">
              {isHe ? "שאלון פרופיל סיכון" : "Risk Profile Questionnaire"}
            </h2>
            <p className="text-gray-400 text-sm mb-6">
              {isHe ? `ענה על ${RISK_QUESTIONS.length} שאלות לקביעת פרופיל ההשקעה שלך` : `Answer ${RISK_QUESTIONS.length} questions to determine your investment profile`}
            </p>

            <div className="space-y-6">
              {RISK_QUESTIONS.map((q, qi) => (
                <div key={q.id}>
                  <p className="font-medium mb-3">
                    {qi + 1}. {isHe ? q.question_he : q.question_en}
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    {q.options.map((opt) => (
                      <button
                        key={opt.value}
                        onClick={() => setAnswers({ ...answers, [q.id]: opt.value })}
                        className={`py-2 px-3 rounded-lg text-sm text-right border transition-colors ${
                          answers[q.id] === opt.value
                            ? "border-blue-500 bg-blue-500/10 text-blue-300"
                            : "border-gray-700 hover:border-gray-600 text-gray-300"
                        }`}
                      >
                        {isHe ? opt.label_he : opt.label_en}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {allAnswered && (
              <div className="mt-6 p-4 bg-gray-800 rounded-xl">
                <p className="text-sm text-gray-400">{isHe ? "פרופיל שלך:" : "Your profile:"}</p>
                <p className={`text-xl font-bold ${profileLabels[riskProfile].color}`}>
                  {isHe ? profileLabels[riskProfile].he : profileLabels[riskProfile].en}
                </p>
                <p className="text-sm text-gray-400">
                  {isHe ? `ציון סיכון: ${riskScore}/100` : `Risk score: ${riskScore}/100`}
                </p>
              </div>
            )}

            <div className="flex gap-3 mt-6">
              <button onClick={() => setStep(0)} className="flex-1 border border-gray-700 rounded-xl py-3 text-gray-400">
                {isHe ? "חזרה" : "Back"}
              </button>
              <button
                onClick={() => setStep(2)}
                disabled={!allAnswered}
                className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-xl py-3 font-medium"
              >
                {isHe ? "המשך" : "Continue"}
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Deposit */}
        {step === 2 && (
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h2 className="text-xl font-bold mb-1">
              {isHe ? "פיקדון ראשוני" : "Initial Deposit"}
            </h2>
            <p className="text-gray-400 text-sm mb-6">
              {isHe ? "כמה ברצונך להפקיד לחשבון ההשקעות שלך?" : "How much would you like to deposit into your investment account?"}
            </p>

            <div className="mb-6">
              <label className="block text-sm text-gray-400 mb-2">
                {isHe ? "סכום (₪)" : "Amount ($)"}
              </label>
              <input
                type="number"
                value={deposit}
                onChange={(e) => setDeposit(Number(e.target.value))}
                min={1000}
                step={1000}
                className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-2xl font-bold text-white focus:outline-none focus:border-blue-500"
              />
            </div>

            <div className="grid grid-cols-4 gap-2 mb-6">
              {[5000, 10000, 25000, 50000].map((amount) => (
                <button
                  key={amount}
                  onClick={() => setDeposit(amount)}
                  className={`py-2 rounded-lg text-sm border ${
                    deposit === amount
                      ? "border-blue-500 bg-blue-500/10 text-blue-300"
                      : "border-gray-700 text-gray-400"
                  }`}
                >
                  {amount.toLocaleString()}
                </button>
              ))}
            </div>

            <div className="mb-6 p-4 bg-gray-800 rounded-xl">
              <p className="text-sm text-gray-400 mb-3">{isHe ? "הגדרות התראות" : "Notification Settings"}</p>
              {[
                { key: "email", he: "דוא\"ל", en: "Email" },
                { key: "sms", he: "SMS", en: "SMS" },
                { key: "push", he: "Push", en: "Push" },
              ].map((ch) => (
                <div key={ch.key} className="flex items-center justify-between py-2">
                  <span className="text-sm">{isHe ? ch.he : ch.en}</span>
                  <button
                    onClick={() => setNotifications({ ...notifications, [ch.key]: !notifications[ch.key as keyof typeof notifications] })}
                    className={`w-10 h-5 rounded-full transition-colors ${
                      notifications[ch.key as keyof typeof notifications] ? "bg-blue-600" : "bg-gray-600"
                    }`}
                  >
                    <div className={`w-4 h-4 bg-white rounded-full mx-0.5 transition-transform ${
                      notifications[ch.key as keyof typeof notifications] ? "translate-x-5" : ""
                    }`} />
                  </button>
                </div>
              ))}
            </div>

            <div className="flex gap-3">
              <button onClick={() => setStep(1)} className="flex-1 border border-gray-700 rounded-xl py-3 text-gray-400">
                {isHe ? "חזרה" : "Back"}
              </button>
              <button
                onClick={() => setStep(3)}
                disabled={deposit < 1000}
                className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-xl py-3 font-medium"
              >
                {isHe ? "המשך" : "Continue"}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Confirm */}
        {step === 3 && (
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h2 className="text-xl font-bold mb-1">
              {isHe ? "אישור פרטים" : "Confirm Details"}
            </h2>

            <div className="space-y-3 mb-6">
              <div className="flex justify-between py-3 border-b border-gray-800">
                <span className="text-gray-400">{isHe ? "פרופיל סיכון" : "Risk Profile"}</span>
                <span className={`font-bold ${profileLabels[riskProfile].color}`}>
                  {isHe ? profileLabels[riskProfile].he : profileLabels[riskProfile].en}
                </span>
              </div>
              <div className="flex justify-between py-3 border-b border-gray-800">
                <span className="text-gray-400">{isHe ? "ציון סיכון" : "Risk Score"}</span>
                <span className="font-bold">{riskScore}/100</span>
              </div>
              <div className="flex justify-between py-3 border-b border-gray-800">
                <span className="text-gray-400">{isHe ? "פיקדון ראשוני" : "Initial Deposit"}</span>
                <span className="font-bold text-green-400">
                  {deposit.toLocaleString()} ₪
                </span>
              </div>
              <div className="flex justify-between py-3">
                <span className="text-gray-400">{isHe ? "התראות" : "Notifications"}</span>
                <span className="font-bold text-sm">
                  {Object.entries(notifications)
                    .filter(([, v]) => v)
                    .map(([k]) => k.toUpperCase())
                    .join(", ")}
                </span>
              </div>
            </div>

            {poolAssets.length > 0 && (
              <div className="mb-6">
                <p className="text-sm text-gray-400 mb-2">
                  {isHe ? "נכסים מומלצים לפרופיל שלך:" : "Recommended assets for your profile:"}
                </p>
                <div className="flex flex-wrap gap-2">
                  {poolAssets.slice(0, 8).map((a) => (
                    <span key={a.symbol} className="px-2 py-1 bg-gray-800 rounded text-xs text-gray-300">
                      {a.symbol}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {error && (
              <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 mb-4 text-red-300 text-sm">
                {error}
              </div>
            )}

            <div className="flex gap-3">
              <button onClick={() => setStep(2)} className="flex-1 border border-gray-700 rounded-xl py-3 text-gray-400">
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
