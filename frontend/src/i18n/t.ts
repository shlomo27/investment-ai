/**
 * UI string translation.
 *
 * The call shape is deliberate:
 *
 *     t("Target price", "מחיר יעד")
 *
 * The English text IS the key. Three things follow from that, and they are
 * the reason it is built this way rather than with symbolic keys:
 *
 *   * A missing translation is impossible. An unknown language, an
 *     un-generated file, a string added yesterday — all fall back to
 *     readable English. There is no such thing as a screen showing
 *     "research.card.target_label" to a user.
 *   * Migrating the existing code is mechanical. Every call site today is
 *     `isHe ? "מחיר יעד" : "Target price"`, which becomes
 *     `t("Target price", "מחיר יעד")` — the same two strings, reordered.
 *   * The source is readable. You can tell what a component says by reading
 *     it, without holding a key file open beside it.
 *
 * Hebrew is passed inline rather than kept in a dictionary because it
 * already exists inline at every call site, and moving it would be a second
 * migration for no gain. Every other language comes from generated files —
 * see scripts/extract-strings.mjs.
 */
import { useAppSelector } from "../store";
import { detectLanguage, isRTL } from "./languages";
import { UI_STRINGS } from "./strings";

export type TFunction = (en: string, he?: string) => string;

/** Resolve one string for a language. Exported for tests and non-React code. */
export function translateUI(en: string, he: string | undefined, lang: string): string {
  if (lang === "en") return en;
  if (lang === "he") return he ?? en;
  // Generated dictionaries are keyed by the English string. A miss is not an
  // error: English is a correct answer, just not the preferred one.
  return UI_STRINGS[lang]?.[en] ?? en;
}

/**
 * The active UI language.
 *
 * The signed-in account's preference wins; before it loads, the device's
 * language is used so the first paint is already right for most readers.
 */
export function useLanguage(): string {
  const user = useAppSelector((s) => s.auth.user);
  return user?.preferred_language || detectLanguage();
}

/**
 * Writing direction for the current language.
 *
 * Driven by the language, not by "is this Hebrew". The app has a second
 * right-to-left language now, and `dir={isHe ? "rtl" : "ltr"}` renders
 * Arabic left-to-right — text that is harder to read than English would
 * have been.
 */
export function useDir(): "rtl" | "ltr" {
  return isRTL(useLanguage()) ? "rtl" : "ltr";
}

/** The translator for the current language. */
export function useT(): TFunction {
  const lang = useLanguage();
  return (en: string, he?: string) => translateUI(en, he, lang);
}
