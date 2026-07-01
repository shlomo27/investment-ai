import React, { useState } from "react";
import { useAppDispatch, useAppSelector } from "../store";
import { updateUserProfile } from "../store/slices/authSlice";
import { authApi } from "../api/client";
import { requestPushPermission } from "../services/pushNotifications";
import { RiskProfile } from "../types";

const PROFILE_META: Record<RiskProfile, { he: string; en: string; color: string }> = {
  [RiskProfile.CONSERVATIVE]: { he: "שמרני",  en: "Conservative", color: "text-blue-400" },
  [RiskProfile.PASSIVE]:      { he: "מאוזן",  en: "Balanced",     color: "text-green-400" },
  [RiskProfile.HYBRID]:       { he: "הייבריד", en: "Hybrid",      color: "text-yellow-400" },
  [RiskProfile.AGGRESSIVE]:   { he: "אגרסיבי", en: "Aggressive",  color: "text-red-400" },
};

const Settings: React.FC = () => {
  const dispatch = useAppDispatch();
  const { user, isLoading } = useAppSelector((s) => s.auth);
  const isHe = user?.preferred_language === "he";

  const [name, setName] = useState(user?.full_name ?? "");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [lang, setLang] = useState<"he" | "en">(user?.preferred_language ?? "he");
  const [notifEmail, setNotifEmail] = useState(user?.notification_email ?? true);
  const [notifSms, setNotifSms] = useState(user?.notification_sms ?? false);
  const [notifPush, setNotifPush] = useState(user?.notification_push ?? false);
  const [ageGroup, setAgeGroup] = useState<string>((user as any)?.age_group ?? "");
  const [horizonMonths, setHorizonMonths] = useState<number>((user as any)?.investment_horizon_months ?? 12);

  const [saved, setSaved] = useState(false);
  const [pushStatus, setPushStatus] = useState<"idle" | "requesting" | "done" | "denied">("idle");

  // 2FA state
  const [twoFAStep, setTwoFAStep] = useState<"idle" | "setup" | "verify" | "disable">("idle");
  const [twoFAQR, setTwoFAQR] = useState<string | null>(null);
  const [twoFASecret, setTwoFASecret] = useState<string | null>(null);
  const [twoFACode, setTwoFACode] = useState("");
  const [twoFAError, setTwoFAError] = useState<string | null>(null);
  const [twoFALoading, setTwoFALoading] = useState(false);
  const [twoFAEnabled, setTwoFAEnabled] = useState((user as any)?.totp_enabled ?? false);

  const AGE_GROUPS = ["18-25", "26-35", "36-50", "50+"];
  const HORIZONS = [
    { months: 3, he: "3 חודשים", en: "3 Months" },
    { months: 6, he: "חצי שנה", en: "6 Months" },
    { months: 12, he: "שנה", en: "1 Year" },
    { months: 36, he: "3 שנים", en: "3 Years" },
    { months: 60, he: "5 שנים", en: "5 Years" },
    { months: 120, he: "10+ שנים", en: "10+ Years" },
  ];

  const profileMeta = user?.risk_profile ? PROFILE_META[user.risk_profile] : null;

  const handleSave = async () => {
    await dispatch(
      updateUserProfile({
        full_name: name,
        phone: phone || undefined,
        preferred_language: lang,
        notification_email: notifEmail,
        notification_sms: notifSms,
        notification_push: notifPush,
        age_group: ageGroup || undefined,
        investment_horizon_months: horizonMonths,
      } as any)
    );
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  const handle2FASetup = async () => {
    setTwoFALoading(true);
    setTwoFAError(null);
    try {
      const res = await authApi.setup2FA();
      setTwoFAQR(res.qr_code);
      setTwoFASecret(res.secret);
      setTwoFAStep("setup");
    } catch {
      setTwoFAError(isHe ? "שגיאה בהגדרת 2FA" : "Failed to setup 2FA");
    } finally {
      setTwoFALoading(false);
    }
  };

  const handle2FAEnable = async () => {
    if (twoFACode.length !== 6) return;
    setTwoFALoading(true);
    setTwoFAError(null);
    try {
      await authApi.enable2FA(twoFACode);
      setTwoFAEnabled(true);
      setTwoFAStep("idle");
      setTwoFACode("");
      setTwoFAQR(null);
    } catch {
      setTwoFAError(isHe ? "קוד שגוי, נסה שוב" : "Invalid code, please try again");
    } finally {
      setTwoFALoading(false);
    }
  };

  const handle2FADisable = async () => {
    if (twoFACode.length !== 6) return;
    setTwoFALoading(true);
    setTwoFAError(null);
    try {
      await authApi.disable2FA(twoFACode);
      setTwoFAEnabled(false);
      setTwoFAStep("idle");
      setTwoFACode("");
    } catch {
      setTwoFAError(isHe ? "קוד שגוי, נסה שוב" : "Invalid code, please try again");
    } finally {
      setTwoFALoading(false);
    }
  };

  const handleEnablePush = async () => {
    setPushStatus("requesting");
    const token = await requestPushPermission();
    if (token) {
      await authApi.updateProfile({ push_token: token, notification_push: true });
      setNotifPush(true);
      setPushStatus("done");
    } else {
      setPushStatus("denied");
    }
  };

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="space-y-6 max-w-xl">
      <h1 className="text-2xl font-bold">{isHe ? "הגדרות" : "Settings"}</h1>

      {saved && (
        <div className="bg-green-900/30 border border-green-700/40 rounded-xl px-4 py-3 text-sm text-green-300">
          {isHe ? "✓ ההגדרות נשמרו בהצלחה" : "✓ Settings saved successfully"}
        </div>
      )}

      {/* ── Profile ─────────────────────────────────────────────────────── */}
      <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800 space-y-4">
        <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">
          {isHe ? "פרופיל אישי" : "Profile"}
        </h2>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-500 block mb-1">{isHe ? "שם מלא" : "Full Name"}</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">{isHe ? "טלפון" : "Phone"}</label>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+972..."
              className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500 placeholder-gray-600"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">{isHe ? "אימייל" : "Email"}</label>
            <p className="text-sm text-gray-400 px-4 py-2.5 bg-gray-800/50 rounded-xl border border-gray-700/50">{user?.email}</p>
          </div>
        </div>

        {profileMeta && (
          <div className="flex items-center gap-3 bg-gray-800/50 rounded-xl px-4 py-3">
            <span className="text-xs text-gray-500">{isHe ? "פרופיל סיכון:" : "Risk profile:"}</span>
            <span className={`text-sm font-bold ${profileMeta.color}`}>
              {isHe ? profileMeta.he : profileMeta.en}
            </span>
            <span className="text-xs text-gray-600 mr-auto">{isHe ? "(הוגדר בהרשמה)" : "(set during onboarding)"}</span>
          </div>
        )}

        {/* Age Group */}
        <div>
          <label className="text-xs text-gray-500 block mb-2">{isHe ? "קבוצת גיל" : "Age Group"}</label>
          <div className="flex gap-2 flex-wrap">
            {AGE_GROUPS.map(a => (
              <button key={a} onClick={() => setAgeGroup(a)} className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                ageGroup === a ? "bg-blue-600/20 border-blue-500 text-blue-300" : "bg-gray-800 border-gray-700 text-gray-400 hover:text-white"
              }`}>{a}</button>
            ))}
          </div>
        </div>

        {/* Investment Horizon */}
        <div>
          <label className="text-xs text-gray-500 block mb-2">{isHe ? "אופק השקעה" : "Investment Horizon"}</label>
          <div className="flex gap-2 flex-wrap">
            {HORIZONS.map(h => (
              <button key={h.months} onClick={() => setHorizonMonths(h.months)} className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                horizonMonths === h.months ? "bg-blue-600/20 border-blue-500 text-blue-300" : "bg-gray-800 border-gray-700 text-gray-400 hover:text-white"
              }`}>{isHe ? h.he : h.en}</button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Language ────────────────────────────────────────────────────── */}
      <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800 space-y-3">
        <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">
          {isHe ? "שפה" : "Language"}
        </h2>
        <div className="flex gap-2">
          {(["he", "en"] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={`flex-1 py-2.5 rounded-xl text-sm font-medium border transition-colors ${
                lang === l ? "bg-blue-600/20 border-blue-500 text-blue-300" : "bg-gray-800 border-gray-700 text-gray-400 hover:text-white"
              }`}
            >
              {l === "he" ? "עברית 🇮🇱" : "English 🇺🇸"}
            </button>
          ))}
        </div>
      </div>

      {/* ── Notifications ───────────────────────────────────────────────── */}
      <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800 space-y-3">
        <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">
          {isHe ? "התרעות" : "Notifications"}
        </h2>

        {[
          { key: "email" as const, icon: "📧", he: "התרעות אימייל",  en: "Email notifications",  val: notifEmail, set: setNotifEmail },
          { key: "sms"   as const, icon: "📱", he: "הודעות SMS",     en: "SMS messages",          val: notifSms,   set: setNotifSms },
          { key: "push"  as const, icon: "🔔", he: "Push (דפדפן)",   en: "Push (browser)",        val: notifPush,  set: setNotifPush },
        ].map((item) => (
          <div key={item.key} className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span>{item.icon}</span>
              <span className="text-sm text-gray-300">{isHe ? item.he : item.en}</span>
            </div>
            <button
              onClick={() => item.set(!item.val)}
              className={`relative w-11 h-6 rounded-full transition-colors ${item.val ? "bg-blue-600" : "bg-gray-700"}`}
            >
              <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${item.val ? "translate-x-5" : "translate-x-0.5"}`} />
            </button>
          </div>
        ))}

        {/* Push activation helper */}
        {!notifPush && (
          <button
            onClick={handleEnablePush}
            disabled={pushStatus === "requesting"}
            className="w-full mt-1 border border-blue-700/50 text-blue-400 hover:bg-blue-900/20 text-sm py-2.5 rounded-xl transition-colors"
          >
            {pushStatus === "requesting" ? (isHe ? "מבקש הרשאה..." : "Requesting permission...")
             : pushStatus === "denied"    ? (isHe ? "ההרשאה נדחתה — אפשר בהגדרות הדפדפן" : "Permission denied — enable in browser settings")
             : pushStatus === "done"      ? (isHe ? "✓ Push הופעל!" : "✓ Push enabled!")
             : (isHe ? "🔔 הפעל התרעות Push" : "🔔 Enable Push Notifications")}
          </button>
        )}
      </div>

      {/* ── Two-Factor Authentication ────────────────────────────────────── */}
      <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">
              {isHe ? "אימות דו-שלבי (2FA)" : "Two-Factor Authentication"}
            </h2>
            <p className="text-xs text-gray-500 mt-1">
              {isHe
                ? "הגן על חשבונך עם Google Authenticator או כל אפליקציית TOTP"
                : "Protect your account with Google Authenticator or any TOTP app"}
            </p>
          </div>
          <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${twoFAEnabled ? "bg-green-900/40 text-green-300" : "bg-gray-800 text-gray-500"}`}>
            {twoFAEnabled ? (isHe ? "פעיל" : "Enabled") : (isHe ? "כבוי" : "Disabled")}
          </span>
        </div>

        {twoFAError && (
          <div className="bg-red-900/30 border border-red-700/40 rounded-xl px-3 py-2 text-xs text-red-300">
            {twoFAError}
          </div>
        )}

        {twoFAStep === "idle" && (
          twoFAEnabled ? (
            <button
              onClick={() => { setTwoFAStep("disable"); setTwoFACode(""); setTwoFAError(null); }}
              className="w-full border border-red-700/50 text-red-400 hover:bg-red-900/20 text-sm py-2.5 rounded-xl transition-colors"
            >
              {isHe ? "בטל אימות דו-שלבי" : "Disable 2FA"}
            </button>
          ) : (
            <button
              onClick={handle2FASetup}
              disabled={twoFALoading}
              className="w-full border border-blue-700/50 text-blue-400 hover:bg-blue-900/20 text-sm py-2.5 rounded-xl transition-colors disabled:opacity-50"
            >
              {twoFALoading ? (isHe ? "מכין..." : "Setting up...") : (isHe ? "🔐 הפעל אימות דו-שלבי" : "🔐 Enable 2FA")}
            </button>
          )
        )}

        {twoFAStep === "setup" && twoFAQR && (
          <div className="space-y-4">
            <p className="text-sm text-gray-300">
              {isHe
                ? "סרוק את קוד ה-QR עם Google Authenticator, לאחר מכן הכנס את הקוד שמוצג:"
                : "Scan the QR code with Google Authenticator, then enter the code shown:"}
            </p>
            <div className="flex justify-center">
              <img src={twoFAQR} alt="2FA QR Code" className="w-48 h-48 rounded-xl border-4 border-white" />
            </div>
            {twoFASecret && (
              <div className="bg-gray-800 rounded-xl px-4 py-2 text-center">
                <p className="text-xs text-gray-500 mb-1">{isHe ? "או הכנס ידנית:" : "Or enter manually:"}</p>
                <code className="text-xs text-blue-300 font-mono tracking-widest">{twoFASecret}</code>
              </div>
            )}
            <div className="flex gap-2">
              <input
                value={twoFACode}
                onChange={(e) => setTwoFACode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="000000"
                maxLength={6}
                className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-center text-lg font-mono tracking-[0.4em] text-white focus:outline-none focus:border-blue-500"
              />
              <button
                onClick={handle2FAEnable}
                disabled={twoFACode.length !== 6 || twoFALoading}
                className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-5 py-2.5 rounded-xl text-sm font-medium transition-colors"
              >
                {twoFALoading ? "..." : (isHe ? "אמת" : "Verify")}
              </button>
            </div>
            <button onClick={() => { setTwoFAStep("idle"); setTwoFAQR(null); }} className="w-full text-gray-500 hover:text-gray-300 text-xs py-1">
              {isHe ? "ביטול" : "Cancel"}
            </button>
          </div>
        )}

        {twoFAStep === "disable" && (
          <div className="space-y-3">
            <p className="text-sm text-gray-300">
              {isHe ? "הכנס את הקוד מהאפליקציה כדי לבטל:" : "Enter your authenticator code to disable:"}
            </p>
            <div className="flex gap-2">
              <input
                value={twoFACode}
                onChange={(e) => setTwoFACode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="000000"
                maxLength={6}
                className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-center text-lg font-mono tracking-[0.4em] text-white focus:outline-none focus:border-blue-500"
              />
              <button
                onClick={handle2FADisable}
                disabled={twoFACode.length !== 6 || twoFALoading}
                className="bg-red-700 hover:bg-red-800 disabled:opacity-50 text-white px-5 py-2.5 rounded-xl text-sm font-medium"
              >
                {twoFALoading ? "..." : (isHe ? "בטל" : "Disable")}
              </button>
            </div>
            <button onClick={() => { setTwoFAStep("idle"); setTwoFACode(""); }} className="w-full text-gray-500 hover:text-gray-300 text-xs py-1">
              {isHe ? "חזור" : "Cancel"}
            </button>
          </div>
        )}
      </div>

      {/* ── Save ────────────────────────────────────────────────────────── */}
      <button
        onClick={handleSave}
        disabled={isLoading}
        className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium py-3 rounded-xl transition-colors"
      >
        {isLoading ? (isHe ? "שומר..." : "Saving...") : (isHe ? "שמור שינויים" : "Save Changes")}
      </button>
    </div>
  );
};

export default Settings;
