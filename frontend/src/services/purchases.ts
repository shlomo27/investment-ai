/**
 * In-app purchases (iOS / Android) via RevenueCat.
 *
 * Apple requires digital subscriptions sold to consumers to go through
 * In-App Purchase. RevenueCat sits in front of StoreKit and Google Play
 * Billing: it validates receipts, survives reinstalls and device changes,
 * and posts the result to our webhook.
 *
 * The division of responsibility matters and is deliberate:
 *
 *   this module   opens the store sheet and reports what the SDK saw
 *   the webhook   is the only thing that grants PRO on the server
 *   /billing/status  is what the app believes
 *
 * The SDK's own customerInfo is never treated as authority. It can be
 * optimistic, restored from a different account, or simply stale — and it
 * runs on a device the user controls. After a purchase the app asks the
 * server, it does not tell it.
 *
 * No web implementation on purpose: the web build must show no purchase UI
 * at all, and Apple's rules forbid the app pointing at an outside payment
 * route. isNative() gates every export here.
 */
import { isNative, isIOS } from "../platform";

/** Entitlement id configured in the RevenueCat dashboard. */
export const PRO_ENTITLEMENT = "pro";

export type Package = {
  identifier: string;
  /** Localised, currency-correct, straight from the store. Never hardcode a price. */
  priceString: string;
  title: string;
  description: string;
};

let configured = false;

/**
 * Start the SDK and bind it to this account.
 *
 * `appUserId` must be our numeric user id: the webhook maps RevenueCat's
 * app_user_id back to a row with it. Without the bind, purchases land on an
 * anonymous RevenueCat id that belongs to no account here and the webhook
 * has nothing to grant.
 */
export async function initPurchases(appUserId: number | string): Promise<void> {
  if (!isNative()) return;

  const apiKey = isIOS()
    ? import.meta.env.VITE_REVENUECAT_IOS_KEY
    : import.meta.env.VITE_REVENUECAT_ANDROID_KEY;

  if (!apiKey) {
    console.warn("[purchases] RevenueCat key missing — purchases disabled in this build");
    return;
  }

  try {
    const { Purchases, LOG_LEVEL } = await import("@revenuecat/purchases-capacitor");
    if (!configured) {
      await Purchases.setLogLevel({ level: LOG_LEVEL.WARN });
      await Purchases.configure({ apiKey, appUserID: String(appUserId) });
      configured = true;
    } else {
      // Same device, different account: re-bind so a purchase is not
      // attributed to whoever signed in first.
      await Purchases.logIn({ appUserID: String(appUserId) });
    }
  } catch (err) {
    console.warn("[purchases] init failed:", err);
  }
}

/** The subscription options to show, priced and localised by the store. */
export async function getPackages(): Promise<Package[]> {
  if (!isNative()) return [];
  try {
    const { Purchases } = await import("@revenuecat/purchases-capacitor");
    const offerings = await Purchases.getOfferings();
    const current = offerings.current;
    if (!current) return [];
    return current.availablePackages.map((p: any) => ({
      identifier: p.identifier,
      priceString: p.product.priceString,
      title: p.product.title,
      description: p.product.description,
    }));
  } catch (err) {
    console.warn("[purchases] getOfferings failed:", err);
    return [];
  }
}

export type PurchaseOutcome =
  | { status: "purchased" }
  | { status: "cancelled" }
  | { status: "error"; message: string };

/**
 * Open the store purchase sheet.
 *
 * A cancellation is a normal outcome, not a failure — showing an error when
 * someone decides not to buy is how an app earns a one-star review.
 */
export async function purchase(packageIdentifier: string): Promise<PurchaseOutcome> {
  if (!isNative()) return { status: "error", message: "Not available on web" };

  try {
    const { Purchases } = await import("@revenuecat/purchases-capacitor");
    const offerings = await Purchases.getOfferings();
    const pkg = offerings.current?.availablePackages.find(
      (p: any) => p.identifier === packageIdentifier
    );
    if (!pkg) return { status: "error", message: "Package unavailable" };

    await Purchases.purchasePackage({ aPackage: pkg });
    return { status: "purchased" };
  } catch (err: any) {
    if (err?.userCancelled || err?.code === "1" || err?.message?.includes("cancel")) {
      return { status: "cancelled" };
    }
    console.warn("[purchases] purchase failed:", err);
    return { status: "error", message: err?.message ?? "Purchase failed" };
  }
}

/**
 * Re-apply a subscription bought earlier — new phone, reinstall, or a
 * purchase whose webhook has not landed yet.
 *
 * Apple REQUIRES a visible "Restore Purchases" control in any app with
 * non-consumable or subscription IAP. Its absence is a documented rejection.
 */
export async function restore(): Promise<boolean> {
  if (!isNative()) return false;
  try {
    const { Purchases } = await import("@revenuecat/purchases-capacitor");
    const { customerInfo } = await Purchases.restorePurchases();
    return Boolean(customerInfo?.entitlements?.active?.[PRO_ENTITLEMENT]);
  } catch (err) {
    console.warn("[purchases] restore failed:", err);
    return false;
  }
}

/** Release the RevenueCat identity on logout so the next user starts clean. */
export async function logoutPurchases(): Promise<void> {
  if (!isNative() || !configured) return;
  try {
    const { Purchases } = await import("@revenuecat/purchases-capacitor");
    await Purchases.logOut();
  } catch {
    /* best effort — logout must never fail on this */
  }
}
