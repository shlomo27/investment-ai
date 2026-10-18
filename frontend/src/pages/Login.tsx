import React, { useState } from "react";
import StatusBarShield from "../components/Layout/StatusBarShield";
import { useT, useDir } from "../i18n/t";
import { LANGUAGES, detectLanguage, rememberLanguage, applyDocumentLanguage } from "../i18n/languages";
import { useNavigate, Link } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../store";
import { loginUser, registerUser, setUser, socialLoginUser } from "../store/slices/authSlice";
import { appleAvailable, googleAvailable, signInWithApple, signInWithGoogle } from "../services/socialLogin";

// Must match TERMS_VERSION in backend/app/api/v1/auth.py. Bump both together
// whenever the substance of /terms.html changes.
const TERMS_VERSION = "2026-09-14";
import { authApi } from "../api/client";

const Login: React.FC = () => {
  const t = useT();
  const dir = useDir();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const { isLoading, error } = useAppSelector((state) => state.auth);

  const [mode, setMode] = useState<"login" | "register">("login");
  // The device's language, not a hardcoded Hebrew. This is the first screen
  // anyone sees and there is no account yet to carry a preference, so the
  // device is the only thing that knows who is reading.
  const [lang, setLang] = useState<string>(() => detectLanguage());

  const [loginForm, setLoginForm] = useState({ email: "", password: "" });
  const [twoFARequired, setTwoFARequired] = useState(false);
  const [preAuthToken, setPreAuthToken] = useState("");
  const [twoFACode, setTwoFACode] = useState("");
  const [twoFAError, setTwoFAError] = useState("");
  const [twoFALoading, setTwoFALoading] = useState(false);
  const [registerForm, setRegisterForm] = useState({
    email: "",
    password: "",
    full_name: "",
    phone: "",
    preferred_language: detectLanguage(),
    // The server rejects registration unless this is true. Unticked by
    // default and never pre-ticked: consent that was pre-ticked is not
    // consent, and this is the record that the risk disclosure was accepted.
    accepted_terms: false,
    accepted_terms_version: TERMS_VERSION,
  });


  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    const result = await dispatch(loginUser(loginForm));
    if (loginUser.fulfilled.match(result)) {
      const payload = result.payload as any;
      if (payload?.requires_2fa) {
        setPreAuthToken(payload.pre_auth_token);
        setTwoFARequired(true);
        return;
      }
      navigate(payload.is_onboarded ? "/dashboard" : "/onboarding");
    }
  };

  const handle2FASubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setTwoFALoading(true);
    setTwoFAError("");
    try {
      const res = await authApi.complete2FALogin(preAuthToken, twoFACode);
      dispatch(setUser(res.user));
      navigate(res.user.is_onboarded ? "/dashboard" : "/onboarding");
    } catch {
      setTwoFAError(t("Invalid code, please try again", "קוד שגוי, נסה שוב"));
    } finally {
      setTwoFALoading(false);
    }
  };

  const [socialError, setSocialError] = useState("");
  const [socialBusy, setSocialBusy] = useState<"apple" | "google" | null>(null);
  const showApple = appleAvailable();
  const showGoogle = googleAvailable();

  const handleSocial = async (provider: "apple" | "google") => {
    setSocialError("");
    setSocialBusy(provider);
    try {
      const r = provider === "apple" ? await signInWithApple() : await signInWithGoogle();
      if (r.status === "cancelled") return;
      if (r.status === "error") {
        setSocialError(t(
          "Sign-in with {provider} did not complete. Try again, or use your email.",
          "הכניסה עם {provider} לא הושלמה. נסה שוב, או היכנס עם אימייל.",
          { provider: provider === "apple" ? "Apple" : "Google" }
        ));
        return;
      }
      const result = await dispatch(socialLoginUser({
        provider, idToken: r.idToken, fullName: r.fullName, preferredLanguage: lang,
      }));
      if (socialLoginUser.fulfilled.match(result)) {
        const payload = result.payload as any;
        if (payload?.requires_2fa) {
          setPreAuthToken(payload.pre_auth_token);
          setTwoFARequired(true);
          return;
        }
        navigate(
          payload.terms_accepted === false ? "/accept-terms"
            : payload.is_onboarded ? "/dashboard" : "/onboarding"
        );
      }
    } finally {
      setSocialBusy(null);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    const result = await dispatch(registerUser(registerForm));
    if (registerUser.fulfilled.match(result)) {
      navigate("/onboarding");
    }
  };

  return (
    <div
      className="min-h-screen bg-gray-950 flex items-center justify-center px-4"
      dir={dir}
      // These screens have no Navbar, and the Navbar is what carried the
      // safe-area inset everywhere else: in the iOS app the logo and the
      // language picker sat under the notch, over the clock and battery.
      style={{ paddingTop: "calc(env(safe-area-inset-top) + 1rem)", paddingBottom: "calc(env(safe-area-inset-bottom) + 1rem)" }}
    >
      <StatusBarShield />
      {/* Language picker.
          A two-way he/en toggle labelled "עב" was wrong twice over for the
          eight other languages: it offered a reader in French a switch to
          Hebrew, and labelled it in an alphabet they may not read. Each
          language names itself, which is the one label every reader of it
          can recognise. */}
      <select
        value={lang}
        onChange={(e) => {
          const code = e.target.value;
          setLang(code);
          rememberLanguage(code);
          applyDocumentLanguage(code);
          setRegisterForm((f) => ({ ...f, preferred_language: code }));
        }}
        aria-label={t("Language", "שפה")}
        style={{ top: "calc(env(safe-area-inset-top) + 1rem)" }}
        className="fixed right-4 bg-gray-900 text-gray-300 text-sm border border-gray-700 rounded px-3 py-1 z-10"
        dir="ltr"
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code}>{l.nativeName}</option>
        ))}
      </select>

      <div className="w-full max-w-md pt-10">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-600 rounded-2xl mb-4">
            <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white">
            {t("Investment AI Platform", "מערכת ניתוח השקעות AI")}
          </h1>
          <p className="text-gray-400 mt-1 text-sm">
            {t("AI-powered portfolio management", "ניהול תיק השקעות מבוסס בינה מלאכותית")}
          </p>
        </div>

        {/* Mode Tabs */}
        <div className="flex bg-gray-900 rounded-xl p-1 mb-6">
          <button
            onClick={() => setMode("login")}
            className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
              mode === "login"
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            {t("Login", "כניסה")}
          </button>
          <button
            onClick={() => setMode("register")}
            className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
              mode === "register"
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            {t("Register", "הרשמה")}
          </button>
        </div>

        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          {error && (
            <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 mb-4 text-red-300 text-sm">
              {error}
            </div>
          )}

          {twoFARequired ? (
            <form onSubmit={handle2FASubmit} className="space-y-4">
              <div className="text-center mb-2">
                <div className="text-3xl mb-2">🔐</div>
                <p className="text-sm text-gray-300 font-medium">
                  {t("Two-Factor Authentication", "אימות דו-שלבי")}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  {t("Enter the code from your authenticator app", "הכנס את הקוד מאפליקציית האימות שלך")}
                </p>
              </div>
              {twoFAError && (
                <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-red-300 text-sm text-center">
                  {twoFAError}
                </div>
              )}
              <input
                value={twoFACode}
                onChange={(e) => setTwoFACode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="000000"
                maxLength={6}
                autoFocus
                className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-center text-2xl font-mono tracking-[0.5em] text-white focus:outline-none focus:border-blue-500"
              />
              <button
                type="submit"
                disabled={twoFACode.length !== 6 || twoFALoading}
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-xl py-3 font-medium transition-colors"
              >
                {twoFALoading ? (t("Verifying...", "מאמת...")) : (t("Verify Login", "אמת כניסה"))}
              </button>
              <button type="button" onClick={() => setTwoFARequired(false)} className="w-full text-gray-500 hover:text-gray-300 text-sm py-1">
                {t("← Back", "← חזור")}
              </button>
            </form>
          ) : mode === "login" ? (
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  {t("Email", "דוא\"ל")}
                </label>
                <input
                  type="email"
                  value={loginForm.email}
                  onChange={(e) => setLoginForm({ ...loginForm, email: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  placeholder={t("Enter email", "הזן דוא\"ל")}
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  {t("Password", "סיסמה")}
                </label>
                <input
                  type="password"
                  value={loginForm.password}
                  onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  placeholder={t("Enter password", "הזן סיסמה")}
                  required
                />
              </div>
              <button
                type="submit"
                disabled={isLoading}
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg py-3 font-medium transition-colors"
              >
                {isLoading ? (t("Logging in...", "מתחבר...")) : (t("Login", "כניסה"))}
              </button>

              {/* Without a way back in, a forgotten password is an uninstall. */}
              <Link
                to="/reset-password"
                className="block text-center text-gray-500 hover:text-gray-300 text-xs pt-1"
              >
                {t("Forgot your password?", "שכחת סיסמה?")}
              </Link>
            </form>
          ) : (
            <form onSubmit={handleRegister} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  {t("Full Name", "שם מלא")}
                </label>
                <input
                  type="text"
                  value={registerForm.full_name}
                  onChange={(e) => setRegisterForm({ ...registerForm, full_name: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  {t("Email", "דוא\"ל")}
                </label>
                <input
                  type="email"
                  value={registerForm.email}
                  onChange={(e) => setRegisterForm({ ...registerForm, email: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  {t("Phone", "טלפון")} <span className="text-red-400">*</span>
                </label>
                <input
                  type="tel"
                  value={registerForm.phone}
                  onChange={(e) => setRegisterForm({ ...registerForm, phone: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  placeholder="+972-50-000-0000"
                  required
                />
                <p className="text-xs text-gray-500 mt-1">
                  {t("Required for receiving recommendation alerts", "נדרש לקבלת התראות על המלצות")}
                </p>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  {t("Password", "סיסמה")}
                </label>
                <input
                  type="password"
                  value={registerForm.password}
                  onChange={(e) => setRegisterForm({ ...registerForm, password: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  minLength={8}
                  required
                />
                <p className="text-xs text-gray-500 mt-1">
                  {t("At least 8 characters including a number", "לפחות 8 תווים כולל ספרה")}
                </p>
              </div>

              {/* Risk disclosure + terms. Unticked by default and required by
                  the server — a pre-ticked box is not consent, and this is the
                  record that the risk warning was accepted. */}
              <div className="bg-amber-500/5 border border-amber-500/30 rounded-lg p-3 space-y-2">
                <p className="text-[11px] text-amber-300/90 leading-relaxed">
                  {t("Trading securities carries risk of loss, including your entire investment. This service provides automated information and analysis only, and is not personal investment advice.", "מסחר בניירות ערך כרוך בסיכון להפסד, לרבות אובדן מלוא ההשקעה. המערכת מספקת מידע וניתוח ממוכן בלבד ואינה מהווה ייעוץ השקעות אישי.")}
                </p>
                <label className="flex items-start gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={registerForm.accepted_terms}
                    onChange={(e) =>
                      setRegisterForm({ ...registerForm, accepted_terms: e.target.checked })
                    }
                    className="mt-0.5 shrink-0 accent-blue-500"
                    required
                  />
                  <span className="text-xs text-gray-300 leading-relaxed">
                    {t("I have read and accept the ", "קראתי ואני מסכים ל")}
                    <a href="/terms.html" target="_blank" rel="noreferrer" className="text-blue-400 underline">
                      {t("Terms of Use", "תנאי השימוש")}
                    </a>
                    {t(" and ", " ול")}
                    <a href="/privacy.html" target="_blank" rel="noreferrer" className="text-blue-400 underline">
                      {t("Privacy Policy", "מדיניות הפרטיות")}
                    </a>
                    {t(", and confirm I am 18 or older.", ", ואני מאשר שאני בן 18 ומעלה.")}
                  </span>
                </label>
              </div>

              <button
                type="submit"
                disabled={isLoading || !registerForm.accepted_terms}
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg py-3 font-medium transition-colors"
              >
                {isLoading ? (t("Registering...", "נרשם...")) : (t("Register", "הרשמה"))}
              </button>
            </form>
          )}

          {/* Apple first: on iOS it is required wherever another provider is
              offered (App Store 4.8), and Apple asks that it be no less
              prominent. Not shown on the 2FA step. */}
          {!twoFARequired && (showApple || showGoogle) && (
            <div className="mt-5">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex-1 h-px bg-gray-800" />
                <span className="text-xs text-gray-500">{t("or", "או")}</span>
                <div className="flex-1 h-px bg-gray-800" />
              </div>
              {socialError && (
                <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 mb-3 text-red-300 text-sm">
                  {socialError}
                </div>
              )}
              <div className="space-y-2.5">
                {showApple && (
                  <button
                    type="button"
                    onClick={() => handleSocial("apple")}
                    disabled={socialBusy !== null}
                    className="w-full flex items-center justify-center gap-2 bg-white text-black rounded-lg py-3 font-medium disabled:opacity-60"
                  >
                    <svg width="18" height="18" viewBox="0 0 384 512" aria-hidden fill="currentColor">
                      <path d="M318.7 268.7c-.2-36.7 16.4-64.4 50-84.8-18.8-26.9-47.2-41.7-84.7-44.6-35.5-2.8-74.3 20.7-88.5 20.7-15 0-49.4-19.7-76.4-19.7C63.3 141.2 4 184.8 4 273.5q0 39.3 14.4 81.2c12.8 36.7 59 126.7 107.2 125.2 25.2-.6 43-17.9 75.8-17.9 31.8 0 48.3 17.9 76.4 17.9 48.6-.7 90.4-82.5 102.6-119.3-65.2-30.7-61.7-90-61.7-91.9zm-56.6-164.2c27.3-32.4 24.8-61.9 24-72.5-24.1 1.4-52 16.4-67.9 34.9-17.5 19.8-27.8 44.3-25.6 71.9 26.1 2 49.9-11.4 69.5-34.3z" />
                    </svg>
                    {socialBusy === "apple" ? t("Signing in...", "מתחבר...") : t("Continue with Apple", "המשך עם Apple")}
                  </button>
                )}
                {showGoogle && (
                  <button
                    type="button"
                    onClick={() => handleSocial("google")}
                    disabled={socialBusy !== null}
                    className="w-full flex items-center justify-center gap-2 bg-gray-800 border border-gray-700 text-white rounded-lg py-3 font-medium hover:border-gray-500 disabled:opacity-60"
                  >
                    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
                      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/>
                      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/>
                      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z"/>
                      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C36.9 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"/>
                    </svg>
                    {socialBusy === "google" ? t("Signing in...", "מתחבר...") : t("Continue with Google", "המשך עם Google")}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        <p className="text-center text-xs text-gray-600 mt-4">
          {t("This platform does not provide regulated investment advice. All decisions are the user's responsibility.", "המערכת אינה מספקת ייעוץ השקעות מוסדר. כל ההחלטות הן באחריות המשתמש.")}
        </p>
      </div>
    </div>
  );
};

export default Login;
