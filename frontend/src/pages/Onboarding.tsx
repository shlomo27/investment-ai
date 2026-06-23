import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../store";
import { completeOnboarding, updateUserProfile } from "../store/slices/authSlice";
import { RiskProfile } from "../types";
import { requestPushPermission } from "../services/pushNotifications";
import { authApi } from "../api/client";

const STEPS = ["welcome", "language", "notifications"] as const;

const Onboarding: React.FC = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const { user, isLoading } = useAppSelector((s) => s.auth);

  const [step, setStep] = useState(0);
  const [lang, setLang] = useState<"he" | "en">(user?.preferred_language ?? "he");
  const [notifs, setNotifs] = useState({ email: true, sms: false, push: false });

  const isHe = lang === "he";

  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const prev = () => setStep((s) => Math.max(s - 1, 0));

  const handleComplete = async () => {
    // Save language preference first so the UI updates immediately
    await dispatch(updateUserProfile({ preferred_language: lang }));

    let pushToken: string | undefined;
    if (notifs.push) {
      const tok = await requestPushPermission();
      if (tok) pushToken = tok;
    }

    const result = await dispatch(
      completeOnboarding({
        risk_profile: RiskProfile.PASSIVE,
        risk_score: 50,
        investment_type: "BOTH",
        allows_volatile: false,
        allows_leveraged: false,
        allows_short: false,
        notification_email: notifs.email,
        notification_sms: notifs.sms,
        notification_push: notifs.push,
      })
    );

    if (pushToken && completeOnboarding.fulfilled.match(result)) {
      await authApi.updateProfile({ push_token: pushToken }).catch(() => {});
    }

    if (completeOnboarding.fulfilled.match(result)) {
      navigate(user?.is_admin ? "/fund" : "/master-list");
    }
  };

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md">

        {/* Progress */}
        <div className="flex gap-2 mb-8">
          {STEPS.map((_, i) => (
            <div key={i} className={`h-1 flex-1 rounded-full transition-colors duration-300 ${i <= step ? "bg-blue-500" : "bg-gray-800"}`} />
          ))}
        </div>

        {/* ── Step 0: Welcome ─────────────────────────────────────────── */}
        {step === 0 && (
          <div className="space-y-6">
            <div className="text-center">
              <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                </svg>
              </div>
              <h1 className="text-2xl font-bold mb-2">
                {isHe ? `ברוך הבא, ${user?.full_name?.split(" ")[0]}!` : `Welcome, ${user?.full_name?.split(" ")[0]}!`}
              </h1>
              <p className="text-gray-400 text-sm leading-relaxed">
                {isHe
                  ? "מערכת ייעוץ השקעות מבוססת AI — מנתחת מאות מניות מדי יום ומספקת המלצות, ניתוחים טכניים והתרעות בזמן אמת."
                  : "AI-powered investment advisory — analyzes hundreds of stocks daily and delivers recommendations, technical analysis, and real-time alerts."}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              {[
                { icon: "🤖", he: "ניתוח כלכלי מלא", en: "Full fundamental analysis" },
                { icon: "📋", he: "רשימת מאסטר רבעונית", en: "Quarterly master list" },
                { icon: "⚡", he: "התרעות חדשות בזמן אמת", en: "Real-time news alerts" },
                { icon: "📊", he: "ניתוח טכני מעמיק", en: "Deep technical analysis" },
              ].map((f) => (
                <div key={f.en} className="bg-gray-900 rounded-xl p-4 border border-gray-800">
                  <p className="text-2xl mb-1">{f.icon}</p>
                  <p className="text-xs text-gray-300">{isHe ? f.he : f.en}</p>
                </div>
              ))}
            </div>

            <button onClick={next} className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 rounded-xl transition-colors">
              {isHe ? "המשך ←" : "Continue →"}
            </button>
          </div>
        )}

        {/* ── Step 1: Language ─────────────────────────────────────────── */}
        {step === 1 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-bold mb-1">{isHe ? "בחר שפה" : "Choose Language"}</h2>
              <p className="text-sm text-gray-400">
                {isHe
                  ? "השפה שתבחר תשפיע על הממשק וגם על ניתוחי ה-AI שתקבל."
                  : "The language you choose affects both the interface and the AI analysis you receive."}
              </p>
            </div>

            <div className="space-y-3">
              {[
                {
                  value: "he" as const,
                  flag: "🇮🇱",
                  title: "עברית",
                  desc: "הממשק וניתוחי ה-AI יוצגו בעברית",
                },
                {
                  value: "en" as const,
                  flag: "🇺🇸",
                  title: "English",
                  desc: "Interface and AI analysis displayed in English",
                },
              ].map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setLang(opt.value)}
                  className={`w-full flex items-center gap-4 px-5 py-4 rounded-xl border text-start transition-all ${
                    lang === opt.value
                      ? "bg-blue-600/20 border-blue-500"
                      : "bg-gray-900 border-gray-800 hover:border-gray-600"
                  }`}
                >
                  <span className="text-3xl">{opt.flag}</span>
                  <div>
                    <p className={`font-semibold ${lang === opt.value ? "text-blue-300" : "text-white"}`}>{opt.title}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{opt.desc}</p>
                  </div>
                  {lang === opt.value && (
                    <span className="mr-auto text-blue-400 text-lg">✓</span>
                  )}
                </button>
              ))}
            </div>

            <div className="flex gap-3">
              <button onClick={prev} className="px-4 py-3 rounded-xl border border-gray-700 text-sm text-gray-400 hover:text-white">
                {isHe ? "חזרה" : "Back"}
              </button>
              <button onClick={next} className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 rounded-xl transition-colors">
                {isHe ? "המשך ←" : "Continue →"}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 2: Notifications ────────────────────────────────────── */}
        {step === 2 && (
          <div className="space-y-5">
            <div>
              <h2 className="text-xl font-bold mb-1">{isHe ? "העדפות התרעות" : "Notification Preferences"}</h2>
              <p className="text-sm text-gray-400">{isHe ? "איך תרצה לקבל עדכונים?" : "How would you like to receive updates?"}</p>
            </div>

            <div className="space-y-2">
              {[
                { key: "email" as const, icon: "📧", he: "התרעות אימייל", en: "Email notifications" },
                { key: "sms"   as const, icon: "📱", he: "הודעות SMS",    en: "SMS messages" },
                { key: "push"  as const, icon: "🔔", he: "Push (דפדפן)",  en: "Push (browser)" },
              ].map((item) => (
                <div key={item.key} className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-xl px-4 py-3">
                  <div className="flex items-center gap-3">
                    <span>{item.icon}</span>
                    <span className="text-sm text-gray-300">{isHe ? item.he : item.en}</span>
                  </div>
                  <button
                    onClick={() => setNotifs((n) => ({ ...n, [item.key]: !n[item.key] }))}
                    className={`relative w-11 h-6 rounded-full transition-colors ${notifs[item.key] ? "bg-blue-600" : "bg-gray-700"}`}
                  >
                    <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${notifs[item.key] ? "translate-x-5" : "translate-x-0.5"}`} />
                  </button>
                </div>
              ))}
            </div>

            <div className="flex gap-3">
              <button onClick={prev} className="px-4 py-3 rounded-xl border border-gray-700 text-sm text-gray-400 hover:text-white">
                {isHe ? "חזרה" : "Back"}
              </button>
              <button
                onClick={handleComplete}
                disabled={isLoading}
                className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white font-bold py-3 rounded-xl transition-colors"
              >
                {isLoading ? (isHe ? "שומר..." : "Saving...") : (isHe ? "✓ כניסה למערכת" : "✓ Enter Platform")}
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
};

export default Onboarding;
