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
