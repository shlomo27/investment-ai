/**
 * Platform detection.
 *
 * The same React bundle runs in three places: a browser on the web build,
 * an Android WebView, and an iOS WKWebView. Most of the app does not care —
 * but the two places it matters are load-bearing:
 *
 *   - API calls. On the web, nginx proxies /api/ to the backend, so a
 *     relative URL works. Natively there is no nginx: the page is served
 *     from capacitor://localhost and a relative /api/v1/... resolves to the
 *     app bundle, which has no such file. Native builds need an absolute URL.
 *
 *   - Push notifications. The web gets an FCM token from the browser's push
 *     service; native gets one from FCM/APNs directly. The backend send path
 *     is identical either way — it just stores whichever token it is given.
 */
import { Capacitor } from "@capacitor/core";

export const isNative = (): boolean => Capacitor.isNativePlatform();

/** "ios" | "android" | "web" */
export const platform = (): string => Capacitor.getPlatform();

export const isIOS = (): boolean => Capacitor.getPlatform() === "ios";
export const isAndroid = (): boolean => Capacitor.getPlatform() === "android";

/**
 * Open a link outside the app, when the URL is only known after an await.
 *
 * window.open() after an await is not a user gesture any more, and both
 * WKWebView and mobile Safari block it silently. In the iOS app the
 * "Connect Telegram" button fetched its link, called window.open, and
 * nothing happened — the screen sat on "waiting for Telegram" with Telegram
 * never opened.
 *
 * Call this synchronously in the click handler, then pass the URL once known:
 *   native  navigate the main frame; Capacitor hands any URL outside the app
 *           to iOS/Android, which opens Telegram (or the browser) directly.
 *   web     open a blank tab now, inside the gesture, and point it at the URL
 *           when it arrives; close it again if fetching the URL fails.
 */
export function openExternalLater(): { go: (url: string) => void; cancel: () => void } {
  if (isNative()) {
    return { go: (url) => { window.location.href = url; }, cancel: () => {} };
  }
  const win = window.open("", "_blank");
  return {
    go: (url) => {
      if (win && !win.closed) win.location.href = url;
      else window.location.href = url;
    },
    cancel: () => { if (win && !win.closed) win.close(); },
  };
}


/**
 * A page of the website (privacy policy, terms) as a link that works here.
 *
 * In the iOS app a relative "/privacy.html" with target="_blank" is handed
 * to the system as capacitor://localhost/privacy.html, which nothing can
 * open, so the links on the purchase screen did nothing at all — and Apple
 * requires them to work. Inside the app they point at the live website.
 */
export function pageUrl(path: string): string {
  // The pages put the reader's language first (Hebrew or English).
  const lang = typeof document !== "undefined" ? document.documentElement.lang : "";
  const withLang = lang ? `${path}?lang=${encodeURIComponent(lang)}` : path;
  if (!isNative()) return withLang;
  const origin = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");
  return origin ? `${origin}${withLang}` : withLang;
}

