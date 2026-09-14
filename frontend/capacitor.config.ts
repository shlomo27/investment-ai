import type { CapacitorConfig } from "@capacitor/cli";

/**
 * Capacitor wraps the existing React build as a native iOS/Android app.
 *
 * ⚠️ appId is the one choice here that CANNOT be changed after the first
 * store submission. Apple and Google both key the app's identity — its
 * reviews, its installed base, its subscriptions — to this string forever.
 * Change it now if the company domain differs; never after publishing.
 */
const config: CapacitorConfig = {
  appId: "com.investmentai.app",
  appName: "Investment AI",

  // Bundle the built assets into the binary. Pointing `server.url` at the
  // Railway deployment instead would ship an app that is literally a remote
  // website in a window — the exact shape App Store guideline 4.2 rejects.
  webDir: "dist",

  // Served from https://localhost on Android, capacitor://localhost on iOS.
  // Both origins must be present in the backend's ALLOWED_ORIGINS.
  server: {
    androidScheme: "https",
  },

  android: {
    // The app talks to Railway over HTTPS only; no cleartext fallback.
    allowMixedContent: false,
  },

  ios: {
    // Charts and tables handle their own insets; let the webview own the
    // full viewport so the layout matches the web build.
    contentInset: "always",
  },

  plugins: {
    PushNotifications: {
      // A signal that arrives while the app is open should still surface —
      // the whole point of the native app is that alerts are not missable.
      presentationOptions: ["badge", "sound", "alert"],
    },
    SplashScreen: {
      launchShowDuration: 1500,
      backgroundColor: "#030712",
      showSpinner: false,
      androidSplashResourceName: "splash",
    },
  },
};

export default config;
