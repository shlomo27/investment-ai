/**
 * Merge translation JSON files into src/i18n/strings.ts.
 *
 *   node scripts/merge-strings.mjs fr=path/to/fr.json de=path/to/de.json
 *
 * Existing entries win. A hand-written or corrected translation is usually
 * better than whatever is being merged in, and a merge that overwrote them
 * would quietly undo someone's work with no diff to argue with.
 *
 * Keys not currently used by any t() call are dropped, so the bundle does
 * not grow a tail of strings from deleted screens.
 */
import { readFileSync, writeFileSync, readdirSync, statSync } from "fs";
import { join } from "path";

const SRC = new URL("../src", import.meta.url).pathname;
const STRINGS = join(SRC, "i18n/strings.ts");

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else if (/\.(tsx?|jsx?)$/.test(p)) out.push(p);
  }
  return out;
}

// Comments are not call sites. Without this the scan reported a key from a
// doc comment that merely quotes a t() call as an example — advice about the
// code counted as the code.
function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:])\/\/[^\n]*/g, (m, p) => p + " ".repeat(m.length - p.length));
}

const CALL = /\bt\(\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g;
const live = new Set();
for (const file of walk(SRC)) {
  for (const m of stripComments(readFileSync(file, "utf8")).matchAll(CALL)) {
    live.add(m[1].slice(1, -1).replace(/\\(["'\\])/g, "$1").replace(/\\n/g, "\n"));
  }
}

const src = readFileSync(STRINGS, "utf8");
const start = src.indexOf("export const UI_STRINGS: StringTable = {");
const header = src.slice(0, start);

// Parse the existing table the same way the checker reads it: by line, so
// this runs with no build step and no dependency on the module compiling.
const table = {};
let current = null;
for (const line of src.slice(start).split("\n")) {
  const lang = line.match(/^  "?([a-z]{2}(?:-[A-Z]{2})?)"?:\s*\{/);
  if (lang) { current = lang[1]; table[current] = {}; continue; }
  if (/^  \},?\s*$/.test(line)) { current = null; continue; }
  const entry = current && line.match(/^\s*"((?:[^"\\]|\\.)*)":\s*"((?:[^"\\]|\\.)*)",?\s*$/);
  if (entry) table[current][JSON.parse(`"${entry[1]}"`)] = JSON.parse(`"${entry[2]}"`);
}

let added = 0, skipped = 0, stale = 0;
for (const arg of process.argv.slice(2)) {
  const [lang, path] = arg.split("=");
  if (!lang || !path) throw new Error(`expected lang=file.json, got: ${arg}`);
  const incoming = JSON.parse(readFileSync(path, "utf8"));
  table[lang] ??= {};
  for (const [key, value] of Object.entries(incoming)) {
    if (!live.has(key)) { stale++; continue; }
    if (key in table[lang]) { skipped++; continue; }
    table[lang][key] = value;
    added++;
  }
}

const body = Object.entries(table)
  .map(([lang, entries]) => {
    const rows = Object.entries(entries)
      .map(([k, v]) => `    ${JSON.stringify(k)}: ${JSON.stringify(v)},`)
      .join("\n");
    return `  ${JSON.stringify(lang)}: {\n${rows}\n  },`;
  })
  .join("\n");

writeFileSync(STRINGS, `${header}export const UI_STRINGS: StringTable = {\n${body}\n};\n`);
console.log(`added ${added}, kept ${skipped} existing, dropped ${stale} no longer used`);
