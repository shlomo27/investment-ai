import React from "react";

/**
 * An opaque strip behind the iOS status bar, for the screens that have no
 * Navbar (sign-in, sign-up completion, onboarding, password reset).
 *
 * The web view runs edge to edge (capacitor.config.ts, ios.contentInset
 * "never"), so on those screens content scrolling up — or pushed up by the
 * keyboard — passed under the clock and battery and read through them. The
 * Navbar is sticky and covers that area itself everywhere else. Zero height
 * where there is no status-bar inset (desktop, Android).
 */
const StatusBarShield: React.FC = () => (
  <div
    aria-hidden
    className="fixed top-0 inset-x-0 bg-gray-950 z-40 pointer-events-none"
    style={{ height: "env(safe-area-inset-top)" }}
  />
);

export default StatusBarShield;
