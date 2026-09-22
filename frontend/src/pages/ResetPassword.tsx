/**
 * Password reset — both halves of the flow.
 *
 * Without a token in the URL it asks for an email address. With one (the
 * link from the reset email) it sets a new password.
 *
 * The request half always reports the same thing, whether or not the address
 * has an account. The server is careful not to leak that difference, and a
 * helpful "no such user" here would hand it straight back — for a financial
 * product, confirming which addresses have accounts tells an attacker who to
 * target.
 */
import React, { useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { authApi } from "../api/client";
import { useT } from "../i18n/t";
import { LANGUAGES, detectLanguage, rememberLanguage, applyDocumentLanguage } from "../i18n/languages";

const ResetPassword: React.FC = () => {
  const t = useT();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token");

  // The app is Hebrew-first and nobody is signed in here, so there is no
  // stored preference to read.
  const [lang, setLang] = useState<string>(() => detectLanguage());
  const isHe = lang === "he";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  const handleRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await authApi.requestPasswordReset(email);
    } catch {
      /* Deliberately ignored. A failure here must look identical to success,
         or the error becomes the enumeration signal the server avoids. */
    }
    setBusy(false);
    setSent(true);
  };

  const handleConfirm = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== confirm) {
      setError(t("Passwords do not match", "הסיסמאות אינן תואמות"));
      return;
    }
    if (password.length < 8 || !/\d/.test(password)) {
      setError(
        t("Password must be at least 8 characters and contain a digit", "הסיסמה חייבת להכיל לפחות 8 תווים וספרה אחת")
      );
      return;
    }

    setBusy(true);
    try {
      await authApi.confirmPasswordReset(token!, password);
      setDone(true);
      setTimeout(() => navigate("/login"), 2500);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : t("Password reset failed", "איפוס הסיסמה נכשל")
      );
    }
    setBusy(false);
  };

  const inputCls =
    "w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500";

  return (
    <div
      dir={isHe ? "rtl" : "ltr"}
      className="min-h-screen bg-gray-950 flex items-center justify-center px-4"
    >
      <div className="w-full max-w-md">
        <div className="flex justify-end mb-3">
      {/* Every language, each named in itself. A two-way he/en control
          offered a reader in French a switch to Hebrew and labelled it in an
          alphabet they may not read. */}
      <select
        value={lang}
        onChange={(e) => {
          const code = e.target.value;
          setLang(code);
          rememberLanguage(code);
          applyDocumentLanguage(code);
        }}
        aria-label={t("Language", "שפה")}
        className="bg-transparent text-xs text-gray-500 hover:text-gray-300 border border-gray-800 rounded px-2 py-1"
        dir="ltr"
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code}>{l.nativeName}</option>
        ))}
      </select>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
          <h1 className="text-xl font-bold text-white mb-1">
            {t("Reset password", "איפוס סיסמה")}
          </h1>

          {/* ── Set a new password ── */}
          {token ? (
            done ? (
              <div className="mt-4 space-y-3">
                <p className="text-green-400 text-sm">
                  {t("Password updated. Taking you to sign in...", "הסיסמה עודכנה. מעביר אותך למסך הכניסה...")}
                </p>
              </div>
            ) : (
              <form onSubmit={handleConfirm} className="mt-4 space-y-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    {t("New password", "סיסמה חדשה")}
                  </label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className={inputCls}
                    autoComplete="new-password"
                    minLength={8}
                    required
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    {t("At least 8 characters including a number", "לפחות 8 תווים כולל ספרה")}
                  </p>
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    {t("Confirm password", "אימות סיסמה")}
                  </label>
                  <input
                    type="password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    className={inputCls}
                    autoComplete="new-password"
                    required
                  />
                </div>

                {error && <p className="text-red-400 text-xs">{error}</p>}

                <button
                  type="submit"
                  disabled={busy}
                  className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg py-3 font-medium"
                >
                  {busy
                    ? t("Updating...", "מעדכן...")
                    : t("Update password", "עדכן סיסמה")}
                </button>
              </form>
            )
          ) : sent ? (
            /* ── Link requested ── */
            <div className="mt-4 space-y-3">
              <p className="text-gray-300 text-sm leading-relaxed">
                {t("If an account exists for that address, a reset link has been sent. The link is valid for 30 minutes.", "אם קיים חשבון עם כתובת זו, נשלח אליו קישור לאיפוס סיסמה. הקישור תקף ל-30 דקות.")}
              </p>
              <p className="text-gray-500 text-xs">
                {t("Didn't arrive? Check your spam folder.", "לא הגיע? בדוק בתיקיית הספאם.")}
              </p>
              <Link to="/login" className="block text-blue-400 text-sm hover:text-blue-300">
                {t("← Back to sign in", "← חזרה לכניסה")}
              </Link>
            </div>
          ) : (
            /* ── Ask for the link ── */
            <form onSubmit={handleRequest} className="mt-4 space-y-4">
              <p className="text-gray-400 text-sm leading-relaxed">
                {t("Enter the email address on the account and we'll send a reset link.", "הזן את כתובת האימייל של החשבון ונשלח אליך קישור לאיפוס.")}
              </p>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  {t("Email", "אימייל")}
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className={inputCls}
                  autoComplete="email"
                  required
                />
              </div>

              <button
                type="submit"
                disabled={busy}
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg py-3 font-medium"
              >
                {busy
                  ? t("Sending...", "שולח...")
                  : t("Send reset link", "שלח קישור לאיפוס")}
              </button>

              <Link
                to="/login"
                className="block text-center text-gray-500 hover:text-gray-300 text-sm"
              >
                {t("Back to sign in", "חזרה לכניסה")}
              </Link>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};

export default ResetPassword;
