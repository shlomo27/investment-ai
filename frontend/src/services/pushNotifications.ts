/**
 * Firebase Cloud Messaging — Web Push Notifications
 *
 * Setup requires these environment variables in .env:
 *   VITE_FIREBASE_API_KEY=...
 *   VITE_FIREBASE_AUTH_DOMAIN=...
 *   VITE_FIREBASE_PROJECT_ID=...
 *   VITE_FIREBASE_MESSAGING_SENDER_ID=...
 *   VITE_FIREBASE_APP_ID=...
 *   VITE_FIREBASE_VAPID_KEY=...
 *
 * If any key is missing, push notifications are silently disabled.
 */

import { isNative } from "../platform";

const FIREBASE_CONFIG = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

const VAPID_KEY = import.meta.env.VITE_FIREBASE_VAPID_KEY;

function isConfigured(): boolean {
  return !!(
    FIREBASE_CONFIG.apiKey &&
    FIREBASE_CONFIG.projectId &&
    FIREBASE_CONFIG.messagingSenderId &&
    FIREBASE_CONFIG.appId &&
    VAPID_KEY
  );
}

/** Register service worker and return its registration */
async function registerSW(): Promise<ServiceWorkerRegistration | null> {
  if (!('serviceWorker' in navigator)) return null;
  try {
    const reg = await navigator.serviceWorker.register('/firebase-messaging-sw.js', { scope: '/' });
    await navigator.serviceWorker.ready;
    // Pass Firebase config to the service worker
    reg.active?.postMessage({ type: 'FIREBASE_CONFIG', config: FIREBASE_CONFIG });
    return reg;
  } catch {
    return null;
  }
}

/**
 * Request push notification permission and return the FCM token.
 * Returns null if permission denied or Firebase is not configured.
 */
async function requestWebPushPermission(): Promise<string | null> {
  if (!isConfigured()) {
    console.warn('[push] Firebase config missing — VITE_FIREBASE_* vars were not baked into this build');
    return null;
  }

  const permission = await Notification.requestPermission();
  if (permission !== 'granted') {
    console.warn('[push] Notification permission not granted:', permission);
    return null;
  }

  try {
    const { initializeApp, getApps } = await import('firebase/app');
    const { getMessaging, getToken } = await import('firebase/messaging');

    const app = getApps().length === 0 ? initializeApp(FIREBASE_CONFIG) : getApps()[0];
    const messaging = getMessaging(app);

    const swReg = await registerSW();
    const token = await getToken(messaging, {
      vapidKey: VAPID_KEY,
      serviceWorkerRegistration: swReg ?? undefined,
    });
    if (!token) console.warn('[push] getToken returned empty token');
    return token || null;
  } catch (err) {
    console.warn('[push] Failed to obtain FCM token:', err);
    return null;
  }
}

/**
 * Initialize push notifications: register SW, get token, save to backend.
 * Call after user is authenticated.
 */
async function initWebPushNotifications(
  savePushToken: (token: string) => Promise<void>
): Promise<void> {
  if (!isConfigured()) return;
  if (!('Notification' in window)) return;

  // Only auto-prompt if already granted — don't interrupt the user on login
  if (Notification.permission === 'granted') {
    const token = await requestWebPushPermission();
    if (token) await savePushToken(token);
  } else {
    // Register SW in background so it's ready when user grants permission later
    registerSW().catch(() => {});
  }
}

// ─── Platform dispatch ───────────────────────────────────────────────────────
//
// Callers (App, Onboarding, Settings) import these two names and stay
// unaware of the platform. The browser keeps the service-worker path above;
// the iOS and Android builds go through the Firebase Messaging plugin,
// which is the only way to get an FCM token — rather than a raw APNs
// token — out of an iPhone. The backend stores whichever string it is
// handed and sends through Firebase either way.
//
// The native module is imported dynamically so its plugin code never lands
// in the browser bundle.

/** Ask for permission and return an FCM token, on whichever platform. */
export async function requestPushPermission(): Promise<string | null> {
  if (isNative()) {
    const { requestNativePushPermission } = await import("./pushNotificationsNative");
    return requestNativePushPermission();
  }
  return requestWebPushPermission();
}

/** Register for push and persist the token. Call once, after login. */
export async function initPushNotifications(
  savePushToken: (token: string) => Promise<void>,
  onOpen?: (path: string) => void
): Promise<void> {
  if (isNative()) {
    const { initNativePush } = await import("./pushNotificationsNative");
    return initNativePush(savePushToken, onOpen);
  }
  return initWebPushNotifications(savePushToken);
}

/** Release the device token on logout so alerts don't follow the next user in. */
export async function teardownPushNotifications(): Promise<void> {
  if (isNative()) {
    const { unregisterNativePush } = await import("./pushNotificationsNative");
    return unregisterNativePush();
  }
}
