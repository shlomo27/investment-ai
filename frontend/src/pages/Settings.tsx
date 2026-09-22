import React, { useEffect, useRef, useState } from "react";
import { useT, useDir , useLocale} from "../i18n/t";
import { useAppDispatch, useAppSelector } from "../store";
import { updateUserProfile, fetchCurrentUser } from "../store/slices/authSlice";
import { authApi } from "../api/client";
import { requestPushPermission } from "../services/pushNotifications";
import { isNative } from "../platform";
import { LANGUAGES, applyDocumentLanguage } from "../i18n/languages";
import Paywall from "../components/Paywall";
import { RiskProfile } from "../types";

const PROFILE_META: Record<RiskProfile, { he: string; en: string; color: string }> = {
  [RiskProfile.CONSERVATIVE]: { he: "שמרני",  en: "Conservative", color: "text-blue-400" },
  [RiskProfile.PASSIVE]:      { he: "מאוזן",  en: "Balanced",     color: "text-green-400" },
  [RiskProfile.HYBRID]:       { he: "הייבריד", en: "Hybrid",      color: "text-yellow-400" },
  [RiskProfile.AGGRESSIVE]:   { he: "אגרסיבי", en: "Aggressive",  color: "text-red-400" },
};

const Settings: React.FC = () => {
  const t = useT();
  const locale = useLocale();
  const dir = useDir();
  const dispatch = useAppDispatch();
  const { user, isLoading } = useAppSelector((s) => s.auth);
  const isHe = user?.preferred_language === "he";

  const [name, setName] = useState(user?.full_name ?? "");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [lang, setLang] = useState<string>(user?.preferred_language ?? "he");
  const [notifEmail, setNotifEmail] = useState(user?.notification_email ?? true);
  const [notifSms, setNotifSms] = useState(user?.notification_sms ?? false);
  const [notifPush, setNotifPush] = useState(user?.notification_push ?? false);
  const [ageGroup, setAgeGroup] = useState<string>((user as any)?.age_group ?? "");
  const [horizonMonths, setHorizonMonths] = useState<number>((user as any)?.investment_horizon_months ?? 12);
  const [alertFreq, setAlertFreq] = useState<"REALTIME" | "EVERY_4_HOURS" | "DAILY">(user?.alert_frequency ?? "REALTIME");
  const [allowsShort, setAllowsShort] = useState<boolean>(user?.allows_short ?? false);
  const [allowsVolatile, setAllowsVolatile] = useState<boolean>(user?.allows_volatile ?? false);

  // Account deletion — required in-app by both stores for any app with sign-up.
  const [delOpen, setDelOpen] = useState(false);
  const [delPassword, setDelPassword] = useState("");
  const [delConfirm, setDelConfirm] = useState("");
  const [delError, setDelError] = useState("");
  const [delLoading, setDelLoading] = useState(false);
  const [paywallOpen, setPaywallOpen] = useState(false);

  const [saved, setSaved] = useState(false);
  const [pushStatus, setPushStatus] = useState<"idle" | "requesting" | "done" | "denied">("idle");

  // Personal Telegram linking
  const [tgLinked, setTgLinked] = useState<boolean>((user as any)?.telegram_linked ?? false);
  const [tgWaiting, setTgWaiting] = useState(false);
  const tgPollRef = useRef<number | null>(null);

  useEffect(() => {
    authApi.telegramStatus().then((s) => setTgLinked(s.linked)).catch(() => {});
    return () => {
      if (tgPollRef.current) window.clearInterval(tgPollRef.current);
    };
  }, []);

  const handleTelegramConnect = async () => {
    try {
      const { link } = await authApi.telegramLinkCode();
      window.open(link, "_blank");
      setTgWaiting(true);
      if (tgPollRef.current) window.clearInterval(tgPollRef.current);
      let attempts = 0;
      tgPollRef.current = window.setInterval(async () => {
        attempts += 1;
        try {
          const s = await authApi.telegramStatus();
          if (s.linked) {
            setTgLinked(true);
            setTgWaiting(false);
            if (tgPollRef.current) window.clearInterval(tgPollRef.current);
          }
        } catch {}
        if (attempts > 60 && tgPollRef.current) {
          window.clearInterval(tgPollRef.current);
          setTgWaiting(false);
        }
      }, 3000);
    } catch {
      setTgWaiting(false);
    }
  };

  const handleTelegramUnlink = async () => {
    try {
      await authApi.telegramUnlink();
      setTgLinked(false);
    } catch {}
  };

  // 2FA state
  const [twoFAStep, setTwoFAStep] = useState<"idle" | "setup" | "verify" | "disable">("idle");
  const [twoFAQR, setTwoFAQR] = useState<string | null>(null);
  const [twoFASecret, setTwoFASecret] = useState<string | null>(null);
  const [twoFACode, setTwoFACode] = useState("");
  const [twoFAError, setTwoFAError] = useState<string | null>(null);
  const [twoFALoading, setTwoFALoading] = useState(false);
  const [twoFAEnabled, setTwoFAEnabled] = useState(user?.totp_enabled ?? false);

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
        alert_frequency: alertFreq,
        allows_short: allowsShort,
        allows_volatile: allowsVolatile,
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
      setTwoFAError(t("Failed to setup 2FA", "שגיאה בהגדרת 2FA"));
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
      setTwoFAError(t("Invalid code, please try again", "קוד שגוי, נסה שוב"));
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
      setTwoFAError(t("Invalid code, please try again", "קוד שגוי, נסה שוב"));
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

  const handleDeleteAccount = async () => {
    setDelError("");
    setDelLoading(true);
    try {
      await authApi.deleteAccount(delPassword);
      // The account is gone; the stored tokens now authenticate nothing.
      localStorage.clear();
      window.location.href = "/login";
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setDelError(
        detail ||
          (t("Could not delete the account", "מחיקת החשבון נכשלה"))
      );
      setDelLoading(false);
    }
  };

  return (
    <div dir={dir} className="space-y-6 max-w-xl">
      {paywallOpen && (
        <Paywall
          isHe={isHe}
          onClose={() => setPaywallOpen(false)}
          onUpgraded={() => {
            setPaywallOpen(false);
            // Re-read the account so the tier shown here — and everywhere
            // else reading user.is_pro — is the upgraded one.
            dispatch(fetchCurrentUser());
          }}
        />
      )}

      <h1 className="text-2xl font-bold">{t("Settings", "הגדרות")}</h1>

      {saved && (
        <div className="bg-green-900/30 border border-green-700/40 rounded-xl px-4 py-3 text-sm text-green-300">
          {t("✓ Settings saved successfully", "✓ ההגדרות נשמרו בהצלחה")}
        </div>
      )}

      {/* ── Profile ─────────────────────────────────────────────────────── */}
      <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800 space-y-4">
        <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">
          {t("Profile", "פרופיל אישי")}
        </h2>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-500 block mb-1">{t("Full Name", "שם מלא")}</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">{t("Phone", "טלפון")}</label>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+972..."
              className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500 placeholder-gray-600"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">{t("Email", "אימייל")}</label>
            <p className="text-sm text-gray-400 px-4 py-2.5 bg-gray-800/50 rounded-xl border border-gray-700/50">{user?.email}</p>
          </div>
        </div>

        {profileMeta && (
          <div className="flex items-center gap-3 bg-gray-800/50 rounded-xl px-4 py-3">
            <span className="text-xs text-gray-500">{t("Risk profile:", "פרופיל סיכון:")}</span>
            <span className={`text-sm font-bold ${profileMeta.color}`}>
              {isHe ? profileMeta.he : profileMeta.en}
            </span>
            <span className="text-xs text-gray-600 mr-auto">{t("(set during onboarding)", "(הוגדר בהרשמה)")}</span>
          </div>
        )}

        {/* Age Group */}
        <div>
          <label className="text-xs text-gray-500 block mb-2">{t("Age Group", "קבוצת גיל")}</label>
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
          <label className="text-xs text-gray-500 block mb-2">{t("Investment Horizon", "אופק השקעה")}</label>
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
          {t("Language", "שפה")}
        </h2>
        <p className="text-xs text-gray-500 leading-relaxed">
          {t("Changes both the interface and the analyses. Defaults to your device language.", "משנה את הממשק ואת הניתוחים. ברירת המחדל נקבעת לפי שפת המכשיר.")}
        </p>
        {/* Every language in one list. A grid rather than a row of buttons:
            ten options do not fit on a phone in a single line, and each one
            is written in its own script so a speaker recognises it without
            reading the rest. */}
        <div className="grid grid-cols-2 gap-2">
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              onClick={() => {
                setLang(l.code);
                // Apply immediately: waiting for Save means picking Arabic
                // leaves the layout left-to-right until the user saves, which
                // reads as the choice not having worked.
                applyDocumentLanguage(l.code);
              }}
              dir={l.rtl ? "rtl" : "ltr"}
              className={`py-2.5 px-3 rounded-xl text-sm font-medium border transition-colors text-center ${
                lang === l.code
                  ? "bg-blue-600/20 border-blue-500 text-blue-300"
                  : "bg-gray-800 border-gray-700 text-gray-400 hover:text-white"
              }`}
            >
              {l.nativeName}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-gray-600 leading-relaxed">
          {t("Analyses are written in English and translated. The first read of an analysis in a new language can take a moment.", "הניתוחים נכתבים באנגלית ומתורגמים. תרגום עשוי לקחת רגע בפעם הראשונה עבור כל ניתוח.")}
        </p>
      </div>

      {/* ── Notifications ───────────────────────────────────────────────── */}
      <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800 space-y-3">
        <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">
          {t("Notifications", "התרעות")}
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

        {/* Alert frequency */}
        <div className="pt-2 border-t border-gray-800">
          <label className="text-xs text-gray-500 block mb-2">
            {t("External alert frequency (Push/SMS/Email)", "תדירות התרעות חיצוניות (Push/SMS/אימייל)")}
          </label>
          <div className="flex gap-2">
            {([
              { key: "REALTIME" as const,      he: "בזמן אמת",       en: "Real-time" },
              { key: "EVERY_4_HOURS" as const, he: "כל 4 שעות",      en: "Every 4h" },
              { key: "DAILY" as const,         he: "פעם ביום",        en: "Daily" },
            ]).map((f) => (
              <button
                key={f.key}
                onClick={() => setAlertFreq(f.key)}
                className={`flex-1 py-2 rounded-xl text-sm border transition-colors ${
                  alertFreq === f.key ? "bg-blue-600/20 border-blue-500 text-blue-300" : "bg-gray-800 border-gray-700 text-gray-400 hover:text-white"
                }`}
              >
                {isHe ? f.he : f.en}
              </button>
            ))}
          </div>
          <p className="text-xs text-gray-600 mt-2">
            {t("The in-app inbox always updates in real time — this only affects external messages.", "תיבת הדואר באפליקציה תמיד מתעדכנת בזמן אמת — ההגדרה משפיעה רק על הודעות חיצוניות.")}
          </p>
        </div>

        {/* Push activation helper */}
        {!notifPush && (
          <button
            onClick={handleEnablePush}
            disabled={pushStatus === "requesting"}
            className="w-full mt-1 border border-blue-700/50 text-blue-400 hover:bg-blue-900/20 text-sm py-2.5 rounded-xl transition-colors"
          >
            {pushStatus === "requesting" ? (t("Requesting permission...", "מבקש הרשאה..."))
             : pushStatus === "denied"    ? (t("Permission denied — enable in browser settings", "ההרשאה נדחתה — אפשר בהגדרות הדפדפן"))
             : pushStatus === "done"      ? (t("✓ Push enabled!", "✓ Push הופעל!"))
             : (t("🔔 Enable Push Notifications", "🔔 הפעל התרעות Push"))}
          </button>
        )}

        {/* Personal Telegram */}
        <div className="pt-3 border-t border-gray-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span>✈️</span>
              <div>
                <span className="text-sm text-gray-300 block">
                  {t("Personal Telegram", "טלגרם אישי")}
                </span>
                <span className="text-xs text-gray-500">
                  {tgLinked
                    ? (t("Linked — personal alerts go to your private chat", "מחובר — התרעות אישיות נשלחות לצ'אט הפרטי שלך"))
                    : (t("Personal portfolio alerts, straight to Telegram", "התרעות אישיות על התיק שלך, ישירות לטלגרם"))}
                </span>
              </div>
            </div>
            {tgLinked ? (
              <button
                onClick={handleTelegramUnlink}
                className="text-xs border border-red-800/60 text-red-400 hover:bg-red-900/20 px-3 py-1.5 rounded-lg transition-colors"
              >
                {t("Unlink", "נתק")}
              </button>
            ) : (
              <button
                onClick={handleTelegramConnect}
                disabled={tgWaiting}
                className="text-xs border border-blue-700/60 text-blue-400 hover:bg-blue-900/20 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-60"
              >
                {tgWaiting
                  ? (t("Waiting for Telegram...", "ממתין לאישור בטלגרם..."))
                  : (t("✈️ Connect Telegram", "✈️ חבר טלגרם אישי"))}
              </button>
            )}
          </div>
          {tgWaiting && (
            <p className="text-xs text-gray-600 mt-2">
              {t('A Telegram window opened — tap "Start" there and linking completes automatically within ~30s.', 'נפתח חלון טלגרם — לחץ שם על "Start" והחיבור יושלם אוטומטית תוך חצי דקה.')}
            </p>
          )}
        </div>
      </div>

      {/* ── Content Preferences ──────────────────────────────────────────── */}
      <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800 space-y-3">
        <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">
          {t("Content Preferences", "העדפות תוכן")}
        </h2>
        <p className="text-xs text-gray-500">
          {t("Choose which signal types appear in your recommendations feed", "בחר אילו סוגי סיגנלים יוצגו לך ברשימת ההמלצות")}
        </p>
        {[
          { icon: "📉", he: "הצג סיגנלים לשורט (מכירה בחסר)", en: "Show short-side signals", val: allowsShort, set: setAllowsShort },
          { icon: "⚡", he: "הצג מניות בתנודתיות גבוהה",       en: "Show high-volatility stocks", val: allowsVolatile, set: setAllowsVolatile },
        ].map((item) => (
          <div key={item.he} className="flex items-center justify-between">
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
      </div>

      {/* ── Two-Factor Authentication ────────────────────────────────────── */}
      <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">
              {t("Two-Factor Authentication", "אימות דו-שלבי (2FA)")}
            </h2>
            <p className="text-xs text-gray-500 mt-1">
              {t("Protect your account with Google Authenticator or any TOTP app", "הגן על חשבונך עם Google Authenticator או כל אפליקציית TOTP")}
            </p>
          </div>
          <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${twoFAEnabled ? "bg-green-900/40 text-green-300" : "bg-gray-800 text-gray-500"}`}>
            {twoFAEnabled ? (t("Enabled", "פעיל")) : (t("Disabled", "כבוי"))}
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
              {t("Disable 2FA", "בטל אימות דו-שלבי")}
            </button>
          ) : (
            <button
              onClick={handle2FASetup}
              disabled={twoFALoading}
              className="w-full border border-blue-700/50 text-blue-400 hover:bg-blue-900/20 text-sm py-2.5 rounded-xl transition-colors disabled:opacity-50"
            >
              {twoFALoading ? (t("Setting up...", "מכין...")) : (t("🔐 Enable 2FA", "🔐 הפעל אימות דו-שלבי"))}
            </button>
          )
        )}

        {twoFAStep === "setup" && twoFAQR && (
          <div className="space-y-4">
            <p className="text-sm text-gray-300">
              {t("Scan the QR code with Google Authenticator, then enter the code shown:", "סרוק את קוד ה-QR עם Google Authenticator, לאחר מכן הכנס את הקוד שמוצג:")}
            </p>
            <div className="flex justify-center">
              <img src={twoFAQR} alt="2FA QR Code" className="w-48 h-48 rounded-xl border-4 border-white" />
            </div>
            {twoFASecret && (
              <div className="bg-gray-800 rounded-xl px-4 py-2 text-center">
                <p className="text-xs text-gray-500 mb-1">{t("Or enter manually:", "או הכנס ידנית:")}</p>
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
                {twoFALoading ? "..." : (t("Verify", "אמת"))}
              </button>
            </div>
            <button onClick={() => { setTwoFAStep("idle"); setTwoFAQR(null); }} className="w-full text-gray-500 hover:text-gray-300 text-xs py-1">
              {t("Cancel", "ביטול")}
            </button>
          </div>
        )}

        {twoFAStep === "disable" && (
          <div className="space-y-3">
            <p className="text-sm text-gray-300">
              {t("Enter your authenticator code to disable:", "הכנס את הקוד מהאפליקציה כדי לבטל:")}
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
                {twoFALoading ? "..." : (t("Disable", "בטל"))}
              </button>
            </div>
            <button onClick={() => { setTwoFAStep("idle"); setTwoFACode(""); }} className="w-full text-gray-500 hover:text-gray-300 text-xs py-1">
              {t("Cancel", "חזור")}
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
        {isLoading ? (t("Saving...", "שומר...")) : (t("Save Changes", "שמור שינויים"))}
      </button>

      {/* ── Subscription ────────────────────────────────────────────────── */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 space-y-3">
        <h2 className="text-sm font-semibold text-gray-300">
          {t("Subscription", "מנוי")}
        </h2>

        {user?.is_pro ? (
          <>
            <div className="flex items-center gap-2">
              <span className="bg-green-500/15 text-green-400 text-xs font-semibold px-2.5 py-1 rounded-full">
                PRO
              </span>
              <span className="text-xs text-gray-400">
                {t("Unlimited tracking and recommendations", "מעקב והמלצות ללא הגבלה")}
              </span>
            </div>
            {user?.subscription_expires_at && (
              <p className="text-xs text-gray-500">
                {t("Renews on ", "מתחדש ב-")}
                {new Date(user.subscription_expires_at).toLocaleDateString(
                  locale
                )}
              </p>
            )}
            <p className="text-[11px] text-gray-500 leading-relaxed">
              {t("Manage or cancel your subscription in your store account settings.", "ניהול או ביטול המנוי מתבצע בהגדרות החשבון בחנות שבה רכשת.")}
            </p>
          </>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <span className="bg-gray-700 text-gray-300 text-xs font-semibold px-2.5 py-1 rounded-full">
                {t("FREE", "חינם")}
              </span>
              <span className="text-xs text-gray-400">
                {t("{stocks} stocks · {recs} recommendations",
                    "מעקב אחרי {stocks} מניות · {recs} המלצות",
                    { stocks: user?.watchlist_limit ?? 2, recs: user?.recommendation_limit ?? 5 })}
              </span>
            </div>
            {/* No purchase route on the web build: Apple forbids the app
                offering or pointing at payment outside In-App Purchase. */}
            {isNative() ? (
              <button
                onClick={() => setPaywallOpen(true)}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 rounded-xl text-sm"
              >
                {t("Upgrade", "שדרג למנוי")}
              </button>
            ) : (
              <p className="text-xs text-gray-500">
                {t("Upgrading is available in the iOS and Android app.", "שדרוג זמין באפליקציה לאייפון ולאנדרואיד.")}
              </p>
            )}
          </>
        )}
      </div>

      {/* ── Delete Account ──────────────────────────────────────────────── */}
      <div className="bg-gray-900 border border-red-900/40 rounded-2xl p-5 space-y-3">
        <h2 className="text-sm font-semibold text-red-400">
          {t("Delete account", "מחיקת חשבון")}
        </h2>
        <p className="text-xs text-gray-400 leading-relaxed">
          {t("Deleting your account is permanent. Your details, portfolio, watchlist and alerts are removed and cannot be restored.", "מחיקת החשבון היא לצמיתות. הפרטים האישיים, התיק, רשימת המעקב וההתראות יימחקו ולא ניתן לשחזר אותם.")}
        </p>

        {!delOpen ? (
          <button
            onClick={() => setDelOpen(true)}
            className="text-red-400 hover:text-red-300 text-sm font-medium underline underline-offset-4"
          >
            {t("I want to delete my account", "אני רוצה למחוק את החשבון")}
          </button>
        ) : (
          <div className="space-y-3 pt-1">
            <input
              type="password"
              value={delPassword}
              onChange={(e) => setDelPassword(e.target.value)}
              autoComplete="current-password"
              placeholder={t("Your password", "הסיסמה שלך")}
              className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-red-500"
            />
            <input
              value={delConfirm}
              onChange={(e) => setDelConfirm(e.target.value)}
              placeholder="DELETE"
              dir="ltr"
              className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-white font-mono tracking-widest focus:outline-none focus:border-red-500"
            />
            <p className="text-[11px] text-gray-500">
              {t("Type DELETE in capitals to confirm.", "הקלד DELETE באותיות גדולות כדי לאשר.")}
            </p>

            {delError && <p className="text-xs text-red-400">{delError}</p>}

            <div className="flex gap-2">
              <button
                onClick={handleDeleteAccount}
                disabled={delConfirm !== "DELETE" || !delPassword || delLoading}
                className="flex-1 bg-red-700 hover:bg-red-800 disabled:opacity-40 text-white px-5 py-2.5 rounded-xl text-sm font-medium"
              >
                {delLoading
                  ? "..."
                  : t("Permanently delete account", "מחק את החשבון לצמיתות")}
              </button>
              <button
                onClick={() => {
                  setDelOpen(false);
                  setDelPassword("");
                  setDelConfirm("");
                  setDelError("");
                }}
                className="text-gray-500 hover:text-gray-300 text-sm px-4"
              >
                {t("Cancel", "ביטול")}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Settings;
