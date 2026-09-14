/**
 * The upgrade screen.
 *
 * Shown when a free account hits a limit, and from Settings. Two rules drive
 * everything here and both come from App Store review:
 *
 *  1. Prices are read from the store, never hardcoded. The store knows the
 *     user's currency, their region's tax, and any promotional price. A
 *     hardcoded "$50/month" is wrong for most of the world and is grounds for
 *     rejection when it disagrees with the sheet the user is shown.
 *
 *  2. "Restore Purchases" is always visible. Apple requires it in any app
 *     with subscription IAP, and its absence is a documented rejection — but
 *     it also matters in practice: it is how someone on a new phone gets back
 *     what they already paid for.
 *
 * On web this renders nothing at all. The app must not show a purchase route
 * outside IAP, and it must not point at one either.
 */
import React, { useEffect, useState } from "react";
import { isNative } from "../platform";
import { getPackages, purchase, restore, type Package } from "../services/purchases";
import { authApi } from "../api/client";

type Props = {
  isHe: boolean;
  /** What the user just tried to do, so the reason is concrete. */
  reason?: "watchlist" | "research" | "recommendations" | null;
  onClose: () => void;
  /** Called once the SERVER confirms PRO — not when the SDK reports success. */
  onUpgraded: () => void;
};

const BENEFITS_HE = [
  "מעקב אחרי מניות ללא הגבלה",
  "כל ההמלצות החיות, לא רק החמש המובילות",
  "הניתוח הכלכלי המלא ונימוקי ועדת ההשקעות",
  "התראות על כל המניות שאתה עוקב אחריהן",
];

const BENEFITS_EN = [
  "Follow unlimited stocks",
  "Every live recommendation, not just the top five",
  "Full fundamental analysis and committee reasoning",
  "Alerts on every stock you follow",
];

const REASON_HE: Record<string, string> = {
  watchlist: "הגעת למכסת המניות בתוכנית החינמית.",
  research: "הניתוח המלא זמין למנויים.",
  recommendations: "יש עוד המלצות חיות שלא מוצגות בתוכנית החינמית.",
};

const REASON_EN: Record<string, string> = {
  watchlist: "You've reached the free plan's stock limit.",
  research: "The full analysis is available to subscribers.",
  recommendations: "There are more live recommendations than the free plan shows.",
};

const Paywall: React.FC<Props> = ({ isHe, reason, onClose, onUpgraded }) => {
  const [packages, setPackages] = useState<Package[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    getPackages()
      .then((p) => alive && setPackages(p))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  // The store SDK saying "purchased" is not the same as the account being
  // upgraded: the webhook has to land first. Poll the server briefly rather
  // than unlocking the UI on the SDK's word and having it snap back.
  const confirmWithServer = async (): Promise<boolean> => {
    for (let attempt = 0; attempt < 6; attempt++) {
      try {
        const status = await authApi.subscriptionStatus();
        if (status.is_pro) return true;
      } catch {
        /* keep trying — a transient failure here is not a failed purchase */
      }
      await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
    }
    return false;
  };

  const handlePurchase = async (identifier: string) => {
    setError("");
    setBusy(true);
    const outcome = await purchase(identifier);

    if (outcome.status === "cancelled") {
      // Deciding not to buy is not an error. Say nothing.
      setBusy(false);
      return;
    }
    if (outcome.status === "error") {
      setError(outcome.message);
      setBusy(false);
      return;
    }

    const confirmed = await confirmWithServer();
    setBusy(false);
    if (confirmed) {
      onUpgraded();
    } else {
      // The money was taken but our server has not seen it yet. Never imply
      // the purchase failed — that sends the user to request a refund for
      // something they successfully bought.
      setError(
        isHe
          ? "הרכישה התקבלה. ההפעלה עשויה לקחת דקה — נסה 'שחזור רכישות' בעוד רגע."
          : "Purchase received. Activation can take a moment — try Restore Purchases shortly."
      );
    }
  };

  const handleRestore = async () => {
    setError("");
    setBusy(true);
    await restore();
    const confirmed = await confirmWithServer();
    setBusy(false);
    if (confirmed) onUpgraded();
    else
      setError(
        isHe ? "לא נמצא מנוי פעיל לשחזור." : "No active subscription found to restore."
      );
  };

  if (!isNative()) return null;

  const benefits = isHe ? BENEFITS_HE : BENEFITS_EN;
  const reasonText = reason ? (isHe ? REASON_HE : REASON_EN)[reason] : null;

  return (
    <div
      dir={isHe ? "rtl" : "ltr"}
      className="fixed inset-0 z-50 bg-gray-950/95 overflow-y-auto"
      role="dialog"
      aria-modal="true"
    >
      <div className="max-w-md mx-auto px-5 py-8 min-h-full flex flex-col">
        <button
          onClick={onClose}
          className="self-start text-gray-500 hover:text-gray-300 text-sm mb-6"
          aria-label={isHe ? "סגור" : "Close"}
        >
          ✕
        </button>

        <h2 className="text-2xl font-bold text-white mb-2">
          {isHe ? "שדרג למנוי" : "Upgrade"}
        </h2>
        {reasonText && <p className="text-blue-400 text-sm mb-5">{reasonText}</p>}

        <ul className="space-y-3 mb-8">
          {benefits.map((b) => (
            <li key={b} className="flex gap-3 text-gray-300 text-sm">
              <span className="text-green-400 shrink-0">✓</span>
              <span>{b}</span>
            </li>
          ))}
        </ul>

        {loading ? (
          <div className="text-gray-500 text-sm">{isHe ? "טוען..." : "Loading..."}</div>
        ) : packages.length === 0 ? (
          <div className="text-gray-400 text-sm">
            {isHe
              ? "המנויים אינם זמינים כרגע. נסה שוב מאוחר יותר."
              : "Subscriptions are unavailable right now. Please try again later."}
          </div>
        ) : (
          <div className="space-y-3">
            {packages.map((p) => (
              <button
                key={p.identifier}
                onClick={() => handlePurchase(p.identifier)}
                disabled={busy}
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-2xl px-5 py-4 text-start"
              >
                <div className="font-semibold">{p.title}</div>
                {/* Price comes from the store, in the user's own currency. */}
                <div className="text-blue-200 text-sm mt-0.5">{p.priceString}</div>
              </button>
            ))}
          </div>
        )}

        {error && <p className="text-amber-400 text-xs mt-4">{error}</p>}

        <button
          onClick={handleRestore}
          disabled={busy}
          className="mt-6 text-gray-400 hover:text-gray-200 text-sm underline underline-offset-4 disabled:opacity-50"
        >
          {isHe ? "שחזור רכישות" : "Restore Purchases"}
        </button>

        <div className="mt-auto pt-8 space-y-2 text-[11px] text-gray-500 leading-relaxed">
          <p>
            {isHe
              ? "המנוי מתחדש אוטומטית עד לביטולו. ניתן לבטל בכל עת דרך הגדרות החשבון בחנות."
              : "Subscription renews automatically until cancelled. Cancel any time in your store account settings."}
          </p>
          {/* Apple requires links to terms and privacy on the purchase screen. */}
          <p className="flex gap-3">
            <a href="/privacy.html" className="underline" target="_blank" rel="noreferrer">
              {isHe ? "מדיניות פרטיות" : "Privacy Policy"}
            </a>
            <a href="/terms.html" className="underline" target="_blank" rel="noreferrer">
              {isHe ? "תנאי שימוש" : "Terms of Use"}
            </a>
          </p>
          <p>
            {isHe
              ? "המערכת מספקת מידע וניתוח בלבד ואינה מהווה ייעוץ השקעות אישי. אין באמור המלצה לביצוע פעולה בניירות ערך."
              : "This service provides information and analysis only. It is not personal investment advice or a recommendation to trade."}
          </p>
        </div>
      </div>
    </div>
  );
};

export default Paywall;
