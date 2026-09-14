/**
 * Push notifications — native (iOS / Android).
 *
 * The web path in ./pushNotifications.ts is unchanged and still owns the
 * browser. This module owns the app builds.
 *
 * Why a separate plugin instead of @capacitor/push-notifications alone:
 * on Android that plugin returns an FCM token, but on iOS it returns the
 * raw APNs device token — 64 hex characters that firebase-admin cannot
 * send to. The backend's _send_push() calls messaging.send(token=...), so
 * an APNs token there fails for every iPhone user, silently, while Android
 * works fine. @capacitor-firebase/messaging returns a real FCM token on
 * both platforms, which means the backend needs no change at all: it keeps
 * storing one string in user.push_token and sending through Firebase.
 *
 * Native setup this depends on (done once, outside the code):
 *   Android — google-services.json in android/app/
 *   iOS     — GoogleService-Info.plist in ios/App/App/
 *             plus an APNs Auth Key (.p8) uploaded to the Firebase project.
 * Without the .p8, iOS push fails silently: registration succeeds, a token
 * is issued, and nothing is ever delivered.
 */
import { FirebaseMessaging } from "@capacitor-firebase/messaging";
import { isNative } from "../platform";

type Navigate = (path: string) => void;

/**
 * Ask for permission and return the FCM token, or null if the user
 * declined. Safe to call on web — returns null without side effects.
 */
export async function requestNativePushPermission(): Promise<string | null> {
  if (!isNative()) return null;

  try {
    const { receive } = await FirebaseMessaging.requestPermissions();
    if (receive !== "granted") {
      console.warn("[push:native] permission not granted:", receive);
      return null;
    }
    const { token } = await FirebaseMessaging.getToken();
    if (!token) {
      console.warn("[push:native] getToken returned empty");
      return null;
    }
    return token;
  } catch (err) {
    console.warn("[push:native] failed to obtain FCM token:", err);
    return null;
  }
}

/**
 * Register listeners and save the token. Call once, after login.
 *
 * `onOpen` receives the in-app path a notification tap should land on, so
 * tapping "BMRN crossed its entry" opens BMRN's research page rather than
 * dumping the user on the dashboard to go find it.
 */
export async function initNativePush(
  savePushToken: (token: string) => Promise<void>,
  onOpen?: Navigate
): Promise<void> {
  if (!isNative()) return;

  try {
    // FCM rotates tokens on reinstall, restore, and occasionally on its own.
    // A stale token is a user who stops receiving alerts and has no way to
    // notice, so persist every rotation rather than only the first token.
    await FirebaseMessaging.addListener("tokenReceived", (event) => {
      if (event?.token) savePushToken(event.token).catch(() => {});
    });

    await FirebaseMessaging.addListener("notificationActionPerformed", (event) => {
      // The backend sends `path` (see _push_data in notifications/service.py),
      // already pointing at /research/<recommendation_id>. Anything else falls
      // back to the dashboard rather than dropping the tap.
      const data = (event?.notification?.data ?? {}) as Record<string, string>;
      if (!onOpen) return;
      onOpen(data.path || "/dashboard");
    });

    const existing = await FirebaseMessaging.checkPermissions();
    if (existing.receive !== "granted") {
      // Don't interrupt on login. The Settings screen asks explicitly, and
      // iOS only ever shows the system prompt once — spending it on an
      // unexplained popup at launch is how apps lose push for good.
      return;
    }

    const token = await requestNativePushPermission();
    if (token) await savePushToken(token);
  } catch (err) {
    console.warn("[push:native] init failed:", err);
  }
}

/** Clear the token so a signed-out device stops receiving another user's alerts. */
export async function unregisterNativePush(): Promise<void> {
  if (!isNative()) return;
  try {
    await FirebaseMessaging.removeAllListeners();
    await FirebaseMessaging.deleteToken();
  } catch {
    /* best effort — logout must never fail on this */
  }
}
