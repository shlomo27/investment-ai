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
export async function requestPushPermission(): Promise<string | null> {
  if (!isConfigured()) return null;

  const permission = await Notification.requestPermission();
  if (permission !== 'granted') return null;

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
    return token || null;
  } catch {
    return null;
  }
}

/**
 * Initialize push notifications: register SW, get token, save to backend.
 * Call after user is authenticated.
 */
export async function initPushNotifications(
  savePushToken: (token: string) => Promise<void>
): Promise<void> {
  if (!isConfigured()) return;
  if (!('Notification' in window)) return;

  // Only auto-prompt if already granted — don't interrupt the user on login
  if (Notification.permission === 'granted') {
    const token = await requestPushPermission();
    if (token) await savePushToken(token);
  } else {
    // Register SW in background so it's ready when user grants permission later
    registerSW().catch(() => {});
  }
}
