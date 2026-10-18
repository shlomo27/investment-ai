/**
 * Sign in with Apple / Google.
 *
 * The plugin talks to the provider on the device and returns its ID token;
 * the server verifies that token (backend app/core/social_auth.py) and signs
 * the user in. Nothing here is trusted on its own — the token is the proof.
 *
 * Availability:
 *   Apple   iOS app only. App Store rule 4.8 requires it there because
 *           Google is offered; on the web it would need a separate Services
 *           ID and domain verification for no gain.
 *   Google  iOS and Android apps, and the web — whenever its client IDs are
 *           configured at build time (VITE_GOOGLE_*). Without them the button
 *           is not shown at all rather than shown and failing.
 */
import { isNative, isIOS } from "../platform";

const WEB_CLIENT_ID = import.meta.env.VITE_GOOGLE_WEB_CLIENT_ID as string | undefined;
const IOS_CLIENT_ID = import.meta.env.VITE_GOOGLE_IOS_CLIENT_ID as string | undefined;

export const appleAvailable = (): boolean => isNative() && isIOS();
export const googleAvailable = (): boolean =>
  isNative() && isIOS() ? !!(IOS_CLIENT_ID && WEB_CLIENT_ID) : !!WEB_CLIENT_ID;

let initialized: Promise<void> | null = null;

async function plugin() {
  const { SocialLogin } = await import("@capgo/capacitor-social-login");
  if (!initialized) {
    initialized = SocialLogin.initialize({
      ...(googleAvailable()
        ? {
            google: {
              webClientId: WEB_CLIENT_ID,
              iOSClientId: IOS_CLIENT_ID,
              // The ID token's audience is the web client on every platform,
              // which is one of the audiences the server accepts.
              iOSServerClientId: WEB_CLIENT_ID,
              mode: "online" as const,
            },
          }
        : {}),
      ...(appleAvailable() ? { apple: { clientId: "com.investmentai.app" } } : {}),
    });
  }
  await initialized;
  return SocialLogin;
}

export type SocialResult =
  | { status: "ok"; idToken: string; fullName?: string }
  | { status: "cancelled" }
  | { status: "error"; message: string };

const cancelled = (err: any) => {
  const m = `${err?.message ?? ""} ${err?.code ?? ""}`.toLowerCase();
  return m.includes("cancel") || m.includes("1001") || m.includes("12501");
};

export async function signInWithApple(): Promise<SocialResult> {
  try {
    const SocialLogin = await plugin();
    const { result } = await SocialLogin.login({
      provider: "apple",
      options: { scopes: ["name", "email"] },
    });
    if (!result.idToken) return { status: "error", message: "No identity token" };
    // Apple sends the name to the device on the FIRST sign-in only, and
    // never in the token — forward it now or the account never gets one.
    const fullName = [result.profile?.givenName, result.profile?.familyName]
      .filter(Boolean).join(" ").trim() || undefined;
    return { status: "ok", idToken: result.idToken, fullName };
  } catch (err: any) {
    if (cancelled(err)) return { status: "cancelled" };
    return { status: "error", message: err?.message ?? "Apple sign-in failed" };
  }
}

export async function signInWithGoogle(): Promise<SocialResult> {
  try {
    const SocialLogin = await plugin();
    const { result } = await SocialLogin.login({
      provider: "google",
      options: { scopes: ["email", "profile"] },
    });
    if (result.responseType !== "online" || !result.idToken) {
      return { status: "error", message: "No identity token" };
    }
    return { status: "ok", idToken: result.idToken, fullName: result.profile?.name ?? undefined };
  } catch (err: any) {
    if (cancelled(err)) return { status: "cancelled" };
    return { status: "error", message: err?.message ?? "Google sign-in failed" };
  }
}
