/**
 * Languages, and which one this reader gets.
 *
 * Mirrors backend/app/core/languages.py. The server is authoritative — the
 * picker is filled from GET /auth/languages — but this list exists so the
 * app can pick a language on the very first paint, before any request has
 * returned. Keep the two in step when adding a language.
 */

export type Language = {
  code: string;
  nativeName: string;
  englishName: string;
  rtl?: boolean;
};

/** English first: it is the source language every analysis is written in. */
export const LANGUAGES: Language[] = [
  { code: "en", nativeName: "English", englishName: "English" },
  { code: "he", nativeName: "עברית", englishName: "Hebrew", rtl: true },
  { code: "de", nativeName: "Deutsch", englishName: "German" },
  { code: "es", nativeName: "Español", englishName: "Spanish" },
  { code: "pt-BR", nativeName: "Português (Brasil)", englishName: "Portuguese (Brazil)" },
  { code: "fr", nativeName: "Français", englishName: "French" },
  { code: "ar", nativeName: "العربية", englishName: "Arabic", rtl: true },
  { code: "it", nativeName: "Italiano", englishName: "Italian" },
  { code: "ko", nativeName: "한국어", englishName: "Korean" },
  { code: "ja", nativeName: "日本語", englishName: "Japanese" },
];

export const DEFAULT_LANGUAGE = "en";

const BY_CODE = new Map(LANGUAGES.map((l) => [l.code, l]));

export const isRTL = (code: string): boolean => Boolean(BY_CODE.get(code)?.rtl);

/**
 * Best supported match for a device tag.
 *
 * Devices report "he-IL", "de-AT", "pt-PT". An exact match wins, then the
 * base subtag, then any regional variant we carry — so a Portuguese speaker
 * in Portugal gets Portuguese rather than English. Unknown falls back to the
 * default, which is a normal thing for a store app to meet, not an error.
 */
export function normalizeLanguage(tag?: string | null): string {
  if (!tag) return DEFAULT_LANGUAGE;
  const t = tag.trim();
  if (BY_CODE.has(t)) return t;

  const lower = t.toLowerCase();
  for (const code of BY_CODE.keys()) {
    if (code.toLowerCase() === lower) return code;
  }
  const base = lower.split(/[-_]/)[0];
  if (BY_CODE.has(base)) return base;
  for (const code of BY_CODE.keys()) {
    if (code.split("-")[0].toLowerCase() === base) return code;
  }
  return DEFAULT_LANGUAGE;
}

const STORAGE_KEY = "app_language";

/**
 * The language to show right now.
 *
 * Order matters:
 *   1. What the user explicitly chose. Their choice outranks everything and
 *      is never silently overridden by a device setting.
 *   2. The device language. An Israeli phone set to Hebrew opens in Hebrew;
 *      the same phone set to English opens in English.
 *   3. English.
 *
 * The signed-in account's stored preference is applied separately, once the
 * profile loads — it cannot be consulted here because this runs before the
 * first request completes.
 */
export function detectLanguage(): string {
  try {
    const chosen = localStorage.getItem(STORAGE_KEY);
    if (chosen && BY_CODE.has(chosen)) return chosen;
  } catch {
    /* private mode or blocked storage — fall through to the device */
  }
  const device =
    typeof navigator !== "undefined"
      ? navigator.languages?.[0] || navigator.language
      : null;
  return normalizeLanguage(device);
}

export function rememberLanguage(code: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    /* best effort: the account preference is the durable copy */
  }
}

/**
 * Point the document at a language and its writing direction.
 *
 * dir has to move with the language or an Arabic reader gets Arabic text in
 * a left-to-right layout, which is harder to read than English would have
 * been.
 */
export function applyDocumentLanguage(code: string): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang = code;
  document.documentElement.dir = isRTL(code) ? "rtl" : "ltr";
}
