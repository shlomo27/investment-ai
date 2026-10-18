import React, { useState } from "react";
import StatusBarShield from "../components/Layout/StatusBarShield";
import { useNavigate } from "react-router-dom";
import { useT, useDir } from "../i18n/t";
import { useAppDispatch, useAppSelector } from "../store";
import { setUser, logoutUser } from "../store/slices/authSlice";
import { authApi } from "../api/client";

// Must match TERMS_VERSION in backend/app/api/v1/auth.py (and Login.tsx).
const TERMS_VERSION = "2026-09-14";

/**
 * The step a password sign-up does on its own form, for an account created
 * by Apple/Google sign-in: accept the terms and the risk disclosure, and
 * optionally leave a phone number for SMS alerts.
 *
 * Every protected route sends such an account here until it is done, so the
 * record that the risk warning was accepted exists for every account,
 * however it was created. The box is never pre-ticked.
 */
const AcceptTerms: React.FC = () => {
  const t = useT();
  const dir = useDir();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const user = useAppSelector((s) => s.auth.user);
  const [accepted, setAccepted] = useState(false);
  const [phone, setPhone] = useState(user?.phone || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const updated = await authApi.acceptTerms({
        accepted_terms_version: TERMS_VERSION,
        phone: phone.trim() || undefined,
      });
      dispatch(setUser(updated));
      navigate(updated.is_onboarded ? "/dashboard" : "/onboarding", { replace: true });
    } catch (err: any) {
      setError(err?.response?.data?.detail?.toString?.() || t("Something went wrong. Please try again.", "משהו השתבש. נסה שוב."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      dir={dir}
      className="min-h-screen bg-gray-950 flex items-center justify-center px-4"
      style={{ paddingTop: "calc(env(safe-area-inset-top) + 1rem)", paddingBottom: "calc(env(safe-area-inset-bottom) + 1rem)" }}
    >
      <StatusBarShield />
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-white">{t("Almost there", "כמעט סיימנו")}</h1>
          {user?.full_name && (
            <p className="text-gray-400 mt-1 text-sm">
              {t("Welcome, {name}", "ברוך הבא, {name}", { name: user.full_name })}
            </p>
          )}
        </div>

        <form onSubmit={submit} className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-4">
          {error && (
            <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-red-300 text-sm">{error}</div>
          )}

          <div>
            <label className="block text-sm text-gray-400 mb-1">
              {t("Phone (optional)", "טלפון (לא חובה)")}
            </label>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
              placeholder="+972-50-000-0000"
              dir="ltr"
            />
            <p className="text-xs text-gray-500 mt-1">
              {t("For SMS alerts. You can add it later in Settings.", "לקבלת התראות ב-SMS. אפשר להוסיף גם אחר כך בהגדרות.")}
            </p>
          </div>

          <div className="bg-amber-500/5 border border-amber-500/30 rounded-lg p-3 space-y-2">
            <p className="text-[11px] text-amber-300/90 leading-relaxed">
              {t("Trading securities carries risk of loss, including your entire investment. This service provides automated information and analysis only, and is not personal investment advice.", "מסחר בניירות ערך כרוך בסיכון להפסד, לרבות אובדן מלוא ההשקעה. המערכת מספקת מידע וניתוח ממוכן בלבד ואינה מהווה ייעוץ השקעות אישי.")}
            </p>
            <label className="flex items-start gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={accepted}
                onChange={(e) => setAccepted(e.target.checked)}
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
            disabled={busy || !accepted}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg py-3 font-medium transition-colors"
          >
            {busy ? t("Saving...", "שומר...") : t("Continue", "המשך")}
          </button>
          <button
            type="button"
            onClick={async () => { await dispatch(logoutUser()); navigate("/login", { replace: true }); }}
            className="w-full text-gray-500 hover:text-gray-300 text-sm py-1"
          >
            {t("Sign out", "התנתק")}
          </button>
        </form>
      </div>
    </div>
  );
};

export default AcceptTerms;
