import React, { useState } from "react";
import { useT, useDir } from "../i18n/t";
import { LANGUAGES, detectLanguage, rememberLanguage, applyDocumentLanguage } from "../i18n/languages";
import { useNavigate, Link } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../store";
import { loginUser, registerUser, setUser } from "../store/slices/authSlice";

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
    >
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
        className="fixed top-4 right-4 bg-gray-900 text-gray-300 text-sm border border-gray-700 rounded px-3 py-1"
        dir="ltr"
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code}>{l.nativeName}</option>
        ))}
      </select>

      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-600 rounded-2xl mb-4">
            <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white">
            {t("Investment AI Platform", "מערכת ייעוץ השקעות AI")}
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
        </div>

        <p className="text-center text-xs text-gray-600 mt-4">
          {t("This platform does not provide regulated investment advice. All decisions are the user's responsibility.", "המערכת אינה מספקת ייעוץ השקעות מוסדר. כל ההחלטות הן באחריות המשתמש.")}
        </p>
      </div>
    </div>
  );
};

export default Login;
