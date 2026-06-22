// Firebase Cloud Messaging Service Worker
// Handles background push notifications when the app is not in the foreground.
importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js');

let messaging = null;

// Receive Firebase config from the main thread and initialize FCM
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'FIREBASE_CONFIG' && !messaging) {
    try {
      const app = firebase.initializeApp(event.data.config);
      messaging = firebase.messaging(app);

      messaging.onBackgroundMessage((payload) => {
        const title = payload.notification?.title || 'Investment AI';
        const body = payload.notification?.body || 'You have a new investment update.';
        self.registration.showNotification(title, {
          body,
          icon: '/favicon.ico',
          badge: '/favicon.ico',
          data: payload.data || {},
          requireInteraction: false,
        });
      });
    } catch (e) {
      // Firebase config invalid or already initialized — ignore
    }
  }
});
