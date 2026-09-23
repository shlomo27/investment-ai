/**
 * Resolve every key in every language the way the app does at render time.
 *
 * i18n-check.mjs compares two lists and can only be as right as its own
 * extraction: it once reported 100% coverage while the bottom navigation on
 * every page fell back to English, because the keys arrived through a data
 * table it was not reading. This does not compare lists — it runs the
 * lookup, and reports four failures a list comparison cannot see:
 *
 *   MISSING    the language has no entry, so the reader gets English
 *   unfilled   a {placeholder} survived substitution
 *   empty      the translation renders as nothing
 *   LOST       a translator dropped a placeholder, so the value it carried —
 *              a price, a count, a company name — vanishes from the sentence
 *
 * Usage: node scripts/i18n-runtime-test.mjs <keys.json>
 */
import { readFileSync } from "fs";

const src = readFileSync(new URL("../src/i18n/strings.ts", import.meta.url).pathname, "utf8");
const table = eval("(" + src.slice(src.indexOf("= {") + 2, src.lastIndexOf("};") + 1) + ")");

function fill(text, vars) {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (w, k) => (k in vars ? String(vars[k]) : w));
}
function translateUI(en, he, lang, vars) {
  if (lang === "en") return fill(en, vars);
  if (lang === "he") return fill(he ?? en, vars);
  return fill(table[lang]?.[en] ?? en, vars);
}

const keys = JSON.parse(readFileSync(process.argv[2], "utf8"));
const langs = Object.keys(table);
// Supply whatever placeholders the key itself declares, so an "unfilled"
// result means the translation dropped or renamed one, not that the test
// forgot to pass it.
const varsFor = (key) => Object.fromEntries(
  [...key.matchAll(/\{(\w+)\}/g)].map((m) => [m[1], "X"])
);

let fellBack = 0, unfilled = 0, empty = 0;
for (const lang of langs) {
  for (const key of keys) {
    const out = translateUI(key, "עברית", lang, varsFor(key));
    if (!(key in (table[lang] ?? {}))) { fellBack++; console.log(`  MISSING   ${lang}  ${JSON.stringify(key)}`); }
    if (/\{\w+\}/.test(out)) { unfilled++; console.log(`  unfilled  ${lang}  ${JSON.stringify(out)}`); }
    if (!out.trim() && key.trim()) { empty++; console.log(`  empty     ${lang}  ${JSON.stringify(key)}`); }
  }
}
console.log(`\n${langs.length} languages x ${keys.length} keys = ${langs.length * keys.length} resolutions`);
console.log(`fell back to English: ${fellBack}   placeholder left unfilled: ${unfilled}   rendered empty: ${empty}`);

// Placeholders must survive into the translation, or the value vanishes.
const WITH_VARS = keys.filter((k) => /\{\w+\}/.test(k));
let lost = 0;
for (const lang of langs) for (const key of WITH_VARS) {
  const raw = table[lang]?.[key];
  if (!raw) continue;
  for (const v of key.match(/\{\w+\}/g)) {
    if (!raw.includes(v)) { lost++; console.log(`  LOST ${v}  ${lang}  ${JSON.stringify(raw)}`); }
  }
}
console.log(`placeholders dropped by a translator: ${lost}`);
process.exit(fellBack + unfilled + empty + lost ? 1 : 0);
