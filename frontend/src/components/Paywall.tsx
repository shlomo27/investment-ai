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
import { isNative, pageUrl } from "../platform";
import { getPackages, purchase, restore, type Package } from "../services/purchases";
import { authApi } from "../api/client";
import { useT } from "../i18n/t";

type Props = {
  isHe: boolean;
  /** What the user just tried to do, so the reason is concrete. */
  reason?: "watchlist" | "research" | "recommendations" | null;
  onClose: () => void;
  /** Called once the SERVER confirms PRO — not when the SDK reports success. */
  onUpgraded: () => void;
};

// One list of pairs rather than two arrays keyed by language: parallel
// BENEFITS_HE / BENEFITS_EN arrays cannot grow a third language without a
// third array, and this is the screen that asks people for money.
const BENEFITS: Array<[string, string]> = [
  ["Follow unlimited stocks", "מעקב אחרי מניות ללא הגבלה"],
  ["Every live recommendation, not just the top five", "כל ההמלצות החיות, לא רק החמש המובילות"],
  ["Full fundamental analysis and committee reasoning", "הניתוח הכלכלי המלא ונימוקי ועדת ההשקעות"],
  ["Alerts on every stock you follow", "התראות על כל המניות שאתה עוקב אחריהן"],
];

const REASONS: Record<string, [string, string]> = {
  watchlist: ["You've reached the free plan's stock limit.", "הגעת למכסת המניות בתוכנית החינמית."],
  research: ["The full analysis is available to subscribers.", "הניתוח המלא זמין למנויים."],
  recommendations: ["There are more live recommendations than the free plan shows.", "יש עוד המלצות חיות שלא מוצגות בתוכנית החינמית."],
};

const Paywall: React.FC<Props> = ({ isHe, reason, onClose, onUpgraded }) => {
  const t = useT();
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
        t("Purchase received. Activation can take a moment — try Restore Purchases shortly.", "הרכישה התקבלה. ההפעלה עשויה לקחת דקה — נסה 'שחזור רכישות' בעוד רגע.")
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
        t("No active subscription found to restore.", "לא נמצא מנוי פעיל לשחזור.")
      );
  };

  if (!isNative()) return null;

  const benefits = BENEFITS.map(([en, he]) => t(en, he));
  const pair = reason ? REASONS[reason] : null;
  const reasonText = pair ? t(pair[0], pair[1]) : null;

  return (
    <div
      dir={isHe ? "rtl" : "ltr"}
      // Opaque: at 95% the Settings screen underneath showed through and
      // its labels ran across the benefits list and the price.
      // Above the bottom tab bar (z-50), which otherwise covered the
      // disclaimer and could take a tap meant for the legal links.
      className="fixed inset-0 z-[60] bg-gray-950 overflow-y-auto"
      role="dialog"
      aria-modal="true"
    >
      <div
        className="max-w-md mx-auto px-5 py-8 min-h-full flex flex-col"
        // Clear of the clock and the home bar on a notched iPhone.
        style={{
          paddingTop: "calc(env(safe-area-inset-top) + 1.5rem)",
          paddingBottom: "calc(env(safe-area-inset-bottom) + 1.5rem)",
        }}
      >
        <button
          onClick={onClose}
          className="self-start text-gray-500 hover:text-gray-300 text-sm mb-6"
          aria-label={t("Close", "סגור")}
        >
          ✕
        </button>

        <h2 className="text-2xl font-bold text-white mb-2">
          {t("Upgrade", "שדרג למנוי")}
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
          <div className="text-gray-500 text-sm">{t("Loading...", "טוען...")}</div>
        ) : packages.length === 0 ? (
          <div className="text-gray-400 text-sm">
            {t("Subscriptions are unavailable right now. Please try again later.", "המנויים אינם זמינים כרגע. נסה שוב מאוחר יותר.")}
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
                {/* Apple requires the billing period beside the price. */}
                <div className="text-blue-200 text-sm mt-0.5">
                  {p.priceString}
                  {p.period === "P1M" ? ` / ${t("month", "חודש")}`
                    : p.period === "P1Y" ? ` / ${t("year", "שנה")}`
                    : ""}
                </div>
                {p.period === "P1M" && (
                  <div className="text-blue-200/80 text-xs mt-1">
                    {t("Monthly subscription, renews automatically", "מנוי חודשי, מתחדש אוטומטית")}
                  </div>
                )}
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
          {t("Restore Purchases", "שחזור רכישות")}
        </button>

        <div className="mt-auto pt-8 space-y-2 text-[11px] text-gray-500 leading-relaxed">
          <p>
            {t("Subscription renews automatically until cancelled. Cancel any time in your store account settings.", "המנוי מתחדש אוטומטית עד לביטולו. ניתן לבטל בכל עת דרך הגדרות החשבון בחנות.")}
          </p>
          {/* Apple requires links to terms and privacy on the purchase screen. */}
          <p className="flex gap-3">
            <a href={pageUrl("/privacy.html")} className="underline" target="_blank" rel="noreferrer">
              {t("Privacy Policy", "מדיניות פרטיות")}
            </a>
            <a href={pageUrl("/terms.html")} className="underline" target="_blank" rel="noreferrer">
              {t("Terms of Use", "תנאי שימוש")}
            </a>
          </p>
          <p>
            {t("This service provides information and analysis only. It is not personal investment advice or a recommendation to trade.", "המערכת מספקת מידע וניתוח בלבד ואינה מהווה ייעוץ השקעות אישי. אין באמור המלצה לביצוע פעולה בניירות ערך.")}
          </p>
        </div>
      </div>
    </div>
  );
};

export default Paywall;
