/**
 * Hebrew text that never reaches the translator.
 *
 * i18n-check.mjs answers "which keys is a language missing", but it can only
 * see strings that already go through t(). A label written straight into the
 * JSX has no key at all, so it is invisible to coverage — it simply shows
 * Hebrew to everyone, in every language, and no percentage ever moves.
 *
 * This finds the opposite case: Hebrew in the source that is NOT inside a
 * t() call. It is how four screens were found serving Hebrew to a French
 * reader while reporting themselves fully covered.
 *
 * Usage:
 *   node scripts/untranslated-scan.mjs
 *   node scripts/untranslated-scan.mjs --strict   # exit 1 if any are found
 */
import { readFileSync, readdirSync, statSync } from "fs";
import { join, relative } from "path";

const SRC = new URL("../src", import.meta.url).pathname;
const ROOT = new URL("..", import.meta.url).pathname;
const HEBREW = /[֐-׿]/;

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else if (/\.(tsx?|jsx?)$/.test(p)) out.push(p);
  }
  return out;
}

// Blank out comments and every t(...) call, then anything Hebrew still
// standing is a string with no way to be translated. Blanking rather than
// deleting keeps the line numbers honest.
function mask(src) {
  let s = src
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:])\/\/[^\n]*/g, (m, p) => p + " ".repeat(m.length - p.length));

  // Balance the parens rather than approximate them with a regex: a t() call
  // can span lines and nest arbitrarily — t("a", "b", { n: f(g(x)) }) — and an
  // approximation reports the tail of a perfectly good call as untranslated.
  const chars = [...s];
  for (let i = 0; i < chars.length - 1; i++) {
    if (chars[i] !== "t" || chars[i + 1] !== "(") continue;
    if (/[\w$.]/.test(chars[i - 1] ?? "")) continue; // .split(, not t(
    let depth = 0;
    let j = i + 1;
    for (; j < chars.length; j++) {
      if (chars[j] === "(") depth++;
      else if (chars[j] === ")" && --depth === 0) break;
    }
    if (j >= chars.length) continue;
    for (let k = i; k <= j; k++) if (chars[k] !== "\n") chars[k] = " ";
  }
  s = chars.join("");

  // `he: "…", en: "…"` and ["English", "עברית"] both reach t() as data, so
  // their Hebrew half is a translation, not a string with no route out.
  s = s.replace(/\b(?:label_)?he\s*:\s*"(?:[^"\\]|\\.)*"/g, (m) => m.replace(/[^\n]/g, " "));
  s = s.replace(/\[\s*"(?:[^"\\]|\\.)*"\s*,\s*"(?:[^"\\]|\\.)*"\s*\]/g, (m) => m.replace(/[^\n]/g, " "));
  return s;
}


const hits = [];
for (const file of walk(SRC)) {
  if (file.includes("/i18n/")) continue; // the dictionaries are meant to be Hebrew
  const raw = readFileSync(file, "utf8");
  const masked = mask(raw);
  masked.split("\n").forEach((line, i) => {
    if (HEBREW.test(line)) {
      hits.push({ file: relative(ROOT, file), line: i + 1, text: raw.split("\n")[i].trim().slice(0, 110) });
    }
  });
}

if (!hits.length) {
  console.log("✓ No Hebrew outside t(). Every user-visible string can be translated.");
} else {
  const byFile = {};
  for (const h of hits) (byFile[h.file] ??= []).push(h);
  console.log(`✗ ${hits.length} line(s) with Hebrew outside a t() call — these show Hebrew in every language:\n`);
  for (const [file, rows] of Object.entries(byFile)) {
    console.log(`  ${file}`);
    for (const r of rows) console.log(`    :${r.line}  ${r.text}`);
  }
}
if (process.argv.includes("--strict") && hits.length) process.exit(1);
