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

const ResetPassword: React.FC = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token");

  // The app is Hebrew-first and nobody is signed in here, so there is no
  // stored preference to read.
  const [lang, setLang] = useState<"he" | "en">("he");
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
      setError(isHe ? "הסיסמאות אינן תואמות" : "Passwords do not match");
      return;
    }
    if (password.length < 8 || !/\d/.test(password)) {
      setError(
        isHe
          ? "הסיסמה חייבת להכיל לפחות 8 תווים וספרה אחת"
          : "Password must be at least 8 characters and contain a digit"
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
          : isHe
          ? "איפוס הסיסמה נכשל"
          : "Password reset failed"
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
          <button
            onClick={() => setLang(isHe ? "en" : "he")}
            className="text-xs text-gray-500 hover:text-gray-300"
          >
            {isHe ? "English" : "עברית"}
          </button>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
          <h1 className="text-xl font-bold text-white mb-1">
            {isHe ? "איפוס סיסמה" : "Reset password"}
          </h1>

          {/* ── Set a new password ── */}
          {token ? (
            done ? (
              <div className="mt-4 space-y-3">
                <p className="text-green-400 text-sm">
                  {isHe
                    ? "הסיסמה עודכנה. מעביר אותך למסך הכניסה..."
                    : "Password updated. Taking you to sign in..."}
                </p>
              </div>
            ) : (
              <form onSubmit={handleConfirm} className="mt-4 space-y-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    {isHe ? "סיסמה חדשה" : "New password"}
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
                    {isHe
                      ? "לפחות 8 תווים כולל ספרה"
                      : "At least 8 characters including a number"}
                  </p>
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    {isHe ? "אימות סיסמה" : "Confirm password"}
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
                    ? isHe
                      ? "מעדכן..."
                      : "Updating..."
                    : isHe
                    ? "עדכן סיסמה"
                    : "Update password"}
                </button>
              </form>
            )
          ) : sent ? (
            /* ── Link requested ── */
            <div className="mt-4 space-y-3">
              <p className="text-gray-300 text-sm leading-relaxed">
                {isHe
                  ? "אם קיים חשבון עם כתובת זו, נשלח אליו קישור לאיפוס סיסמה. הקישור תקף ל-30 דקות."
                  : "If an account exists for that address, a reset link has been sent. The link is valid for 30 minutes."}
              </p>
              <p className="text-gray-500 text-xs">
                {isHe
                  ? "לא הגיע? בדוק בתיקיית הספאם."
                  : "Didn't arrive? Check your spam folder."}
              </p>
              <Link to="/login" className="block text-blue-400 text-sm hover:text-blue-300">
                {isHe ? "← חזרה לכניסה" : "← Back to sign in"}
              </Link>
            </div>
          ) : (
            /* ── Ask for the link ── */
            <form onSubmit={handleRequest} className="mt-4 space-y-4">
              <p className="text-gray-400 text-sm leading-relaxed">
                {isHe
                  ? "הזן את כתובת האימייל של החשבון ונשלח אליך קישור לאיפוס."
                  : "Enter the email address on the account and we'll send a reset link."}
              </p>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  {isHe ? "אימייל" : "Email"}
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
                  ? isHe
                    ? "שולח..."
                    : "Sending..."
                  : isHe
                  ? "שלח קישור לאיפוס"
                  : "Send reset link"}
              </button>

              <Link
                to="/login"
                className="block text-center text-gray-500 hover:text-gray-300 text-sm"
              >
                {isHe ? "חזרה לכניסה" : "Back to sign in"}
              </Link>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};

export default ResetPassword;
