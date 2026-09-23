/**
 * Two questions about the UI strings that nobody can answer by reading.
 *
 *   1. Which t() calls can NEVER be translated?
 *      The English text is the dictionary key, so a key built with a
 *      template literal changes with its values. `t(`${symbol} is cheaper`)`
 *      needs one entry per ticker; `t(`entry $${price}`)` needs one per
 *      price, and the price changes on every scan. These are not "not yet
 *      translated" — no dictionary can ever hold them. They are errors.
 *      The fix is a placeholder: t("entry {price}", ..., { price }).
 *
 *   2. Which keys is each language missing?
 *      A miss falls back to English, which is readable but not what the
 *      reader chose. Half a screen in French and half in English is what
 *      this reports, before a user finds it.
 *
 * Usage:
 *   node scripts/i18n-check.mjs          # report
 *   node scripts/i18n-check.mjs --strict # exit 1 on interpolated keys
 */
import { readFileSync, readdirSync, statSync } from "fs";
import { join, relative } from "path";

const SRC = new URL("../src", import.meta.url).pathname;
const ROOT = new URL("..", import.meta.url).pathname;

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else if (/\.(tsx?|jsx?)$/.test(p)) out.push(p);
  }
  return out;
}

// t( and translateUI( calls, capturing the first argument's opening quote.
// Deliberately not a parser: it only has to tell a backtick that contains
// ${ from every other first argument, and be obvious enough to trust.
// Comments are not call sites. Without this the scan reported a key from a
// doc comment that merely quotes a t() call as an example — advice about the
// code counted as the code.
function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:])\/\/[^\n]*/g, (m, p) => p + " ".repeat(m.length - p.length));
}

// Keys that reach t() through a data table rather than a literal:
//
//     const TABS = [{ he: "מעקב", en: "Watchlist" }, ...]
//     <span>{t(tab.en, tab.he)}</span>
//
// The call site has no string in it, so a scan that only reads t() arguments
// reports these screens as having nothing to translate while the navigation
// on every page depends on them. The English side of such a pair is a key.
const PAIRED = /\b(?:label_)?he\s*:\s*"(?:[^"\\]|\\.)*"\s*,\s*(?:label_)?en\s*:\s*("(?:[^"\\]|\\.)*")/g;

const CALL = /\bt\(\s*(`[^`]*`|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g;

const interpolated = [];
const keys = new Set();

for (const file of walk(SRC)) {
  const text = stripComments(readFileSync(file, "utf8"));
  const lines = text.split("\n");
  for (const m of text.matchAll(CALL)) {
    const raw = m[1];
    const line = text.slice(0, m.index).split("\n").length;
    if (raw.startsWith("`")) {
      if (raw.includes("${")) {
        interpolated.push({
          file: relative(ROOT, file),
          line,
          snippet: lines[line - 1].trim().slice(0, 100),
        });
        continue;
      }
      keys.add(raw.slice(1, -1));
    } else {
      // Unescape only what a source string can carry.
      keys.add(raw.slice(1, -1).replace(/\\(["'\\])/g, "$1").replace(/\\n/g, "\n"));
    }
  }
  for (const m of text.matchAll(PAIRED)) {
    keys.add(m[1].slice(1, -1).replace(/\\(["'\\\\])/g, "$1"));
  }
}

// A binding named `t` that is not the translator.
//
// `.map((t: any) => ... t("sold", "מכר") ...)` type-checks — `any` is
// callable — and then throws at runtime, because `t` is a trade object. The
// inbox crashed this way. Any parameter or local named `t` shadows the
// translator for its whole scope, so the name is simply not available.
const SHADOW = /(?:\(|,\s*)(t)\s*(?::\s*(?!TFunction)[^,)=]+)?\s*(?:=>|[,)])|\b(?:const|let|var)\s+(t)\s*=(?!\s*useT\(\))/g;
const shadows = [];
for (const file of walk(SRC)) {
  if (file.includes("/i18n/")) continue;
  const text = stripComments(readFileSync(file, "utf8"));
  const lines = text.split("\n");
  for (const m of text.matchAll(SHADOW)) {
    const line = text.slice(0, m.index).split("\n").length;
    const src = lines[line - 1];
    if (/\bconst t = useT\(\)/.test(src)) continue;
    if (/\bt\s*:\s*TFunction/.test(src)) continue;
    // A translator that cannot use the hook (a class component) is still
    // the translator, and `f(t)` passes it rather than rebinding it.
    if (/translateUI\(/.test(src)) continue;
    if (/\w\(t\)/.test(src)) continue;
    shadows.push({ file: relative(ROOT, file), line, snippet: src.trim().slice(0, 100) });
  }
}
if (shadows.length) {
  console.log(`✗ ${shadows.length} binding(s) named \`t\` that shadow the translator:\n`);
  for (const sdw of shadows) console.log(`    ${sdw.file}:${sdw.line}\n      ${sdw.snippet}`);
  console.log("");
} else {
  console.log("✓ Nothing shadows the translator.\n");
}

// The dictionary is a TS module; read it as text rather than importing, so
// this runs without a build step.
const stringsSrc = readFileSync(join(SRC, "i18n/strings.ts"), "utf8");
const body = stringsSrc.slice(stringsSrc.indexOf("UI_STRINGS: StringTable = {"));
const langs = {};
let current = null;
for (const line of body.split("\n")) {
  const lang = line.match(/^  "?([a-z]{2}(?:-[A-Z]{2})?)"?:\s*\{/);
  if (lang) { current = lang[1]; langs[current] = new Set(); continue; }
  if (/^  \},?\s*$/.test(line)) { current = null; continue; }
  const entry = current && line.match(/^\s*"((?:[^"\\]|\\.)*)":/);
  if (entry) langs[current].add(entry[1].replace(/\\(["'\\])/g, "$1"));
}

console.log(`Scanned ${keys.size} translatable keys across ${walk(SRC).length} files.\n`);

if (interpolated.length) {
  console.log(`✗ ${interpolated.length} key(s) built from a template literal — these can never be translated:\n`);
  for (const i of interpolated) console.log(`    ${i.file}:${i.line}\n      ${i.snippet}`);
  console.log("\n  Fix: move the value into a placeholder —");
  console.log('      t("entry {price}", "בהמלצה {price}", { price })\n');
} else {
  console.log("✓ No interpolated keys. Every string has a stable key.\n");
}

const names = Object.keys(langs);
if (!names.length) console.log("No dictionaries found in src/i18n/strings.ts.");
else {
  console.log("Coverage:");
  for (const lang of names) {
    const have = [...keys].filter((k) => langs[lang].has(k)).length;
    const pct = keys.size ? ((have / keys.size) * 100).toFixed(0) : "0";
    const missing = keys.size - have;
    console.log(`  ${lang.padEnd(6)} ${String(have).padStart(4)}/${keys.size}  ${pct.padStart(3)}%` +
      (missing ? `   (${missing} fall back to English)` : ""));
  }
  const detail = process.argv.includes("--missing");
  if (detail) {
    for (const lang of names) {
      const missing = [...keys].filter((k) => !langs[lang].has(k));
      if (!missing.length) continue;
      console.log(`\n  ${lang} is missing:`);
      for (const k of missing) console.log(`    ${JSON.stringify(k)}`);
    }
  } else {
    console.log("\n  Run with --missing to list the untranslated keys.");
  }
}

if (process.argv.includes("--strict") && (interpolated.length || shadows.length)) process.exit(1);
