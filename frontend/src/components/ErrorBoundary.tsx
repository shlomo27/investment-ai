/**
 * Catches a render error and shows something, instead of nothing.
 *
 * React unmounts the whole tree when a render throws. With no boundary the
 * result is a blank screen — no message, no way back, nothing to report. One
 * undefined field in one panel takes down the entire page: rendering the
 * admin dashboard against an endpoint returning an unexpected shape produced
 * exactly that, a completely empty document with only a console error nobody
 * on a phone can see.
 *
 * That matters beyond tidiness. A store reviewer who hits a blank screen does
 * not file a bug — they reject the app, and "the app crashed on launch" is
 * not a rejection you can argue with.
 */
import { translateUI } from "../i18n/t";
import { detectLanguage } from "../i18n/languages";
import React from "react";

type Props = {
  children: React.ReactNode;
  isHe?: boolean;
  /** Shown instead of the default panel, when a caller wants its own. */
  fallback?: React.ReactNode;
};

type State = { error: Error | null };

class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Keep the detail in the console for a developer; the screen stays calm.
    console.error("[ui] render failed:", error, info.componentStack);
  }

  handleReload = () => {
    // A full reload rather than resetting state: whatever produced the bad
    // data is usually cached in the store, so re-rendering the same tree
    // would just throw again.
    window.location.reload();
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return <>{this.props.fallback}</>;

    const isHe = this.props.isHe ?? true;
    // No hook here: a class is the only thing that can catch a render
    // error, so the language is read directly instead.
    const lang = detectLanguage();
    const t = (en: string, he: string) => translateUI(en, he, lang);

    return (
      <div
        dir={isHe ? "rtl" : "ltr"}
        className="min-h-[60vh] flex items-center justify-center p-6"
      >
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 max-w-sm w-full text-center space-y-4">
          <p className="text-3xl">⚠️</p>
          <h2 className="text-white font-semibold">
            {t("Something went wrong loading this screen", "משהו השתבש בטעינת המסך")}
          </h2>
          <p className="text-gray-400 text-sm leading-relaxed">
            {t("Your data is safe. Try reloading — if it keeps happening, tell us what you were doing.", "הנתונים שלך בטוחים. נסה לטעון מחדש — אם זה חוזר, ספר לנו מה ניסית לעשות.")}
          </p>
          <button
            onClick={this.handleReload}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 rounded-xl text-sm"
          >
            {t("Reload", "טען מחדש")}
          </button>
          {/* The message only — never a stack trace. It is unreadable on a
              phone and can disclose internals. */}
          <p className="text-[11px] text-gray-600 font-mono break-words">
            {error.message?.slice(0, 120)}
          </p>
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;
