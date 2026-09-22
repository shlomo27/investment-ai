/**
 * Fill src/i18n/strings.ts for a language.
 *
 * Extracts every English key from the t("English", "עברית") call sites,
 * translates the ones that language is missing, and writes them back.
 *
 *   OPENAI_API_KEY=sk-... node scripts/translate-ui.mjs fr
 *   OPENAI_API_KEY=sk-... node scripts/translate-ui.mjs ar ko ja
 *
 * Run at build time, not at runtime: UI labels must be in the bundle so the
 * first paint is already correct. A label fetched after render shows the
 * reader English and then swaps it, which looks like a bug.
 *
 * Existing entries are never overwritten. Hand-written translations are
 * usually better than generated ones, and a regeneration that silently
 * replaced them would quietly undo someone's corrections.
 */
import fs from "node:fs";
import path from "node:path";

const SRC = "src";
const STRINGS = "src/i18n/strings.ts";
const MODEL = process.env.OPENAI_MODEL || "gpt-4o-mini";

const LANGUAGE_NAMES = {
  fr: "French", es: "Spanish", de: "German", "pt-BR": "Brazilian Portuguese",
  ar: "Arabic", it: "Italian", ko: "Korean", ja: "Japanese", he: "Hebrew",
};

/** Every English key used by a t() call, across the source tree. */
function collectKeys(dir = SRC, found = new Set()) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) { collectKeys(full, found); continue; }
    if (!/\.tsx?$/.test(entry.name)) continue;
    const text = fs.readFileSync(full, "utf8");
    // t("English", "Hebrew")  — double-quoted, escapes allowed.
    const re = /\bt\(\s*"((?:[^"\\]|\\.)*)"\s*(?:,|\))/g;
    let m;
    while ((m = re.exec(text))) {
      const key = m[1].replace(/\\"/g, '"');
      // Skip interpolated or trivial fragments — they are not real labels.
      if (key.length > 1 && !key.includes("${")) found.add(key);
    }
  }
  return found;
}

async function translateBatch(keys, lang) {
  const name = LANGUAGE_NAMES[lang] || lang;
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error("OPENAI_API_KEY is not set");

  const system =
    `You translate user-interface labels for a stock analysis app into ${name}.\n` +
    "Return ONLY a JSON object mapping each English string to its translation.\n" +
    "Rules:\n" +
    "1. These are UI labels — buttons, headings, table columns. Keep them SHORT. " +
    "A label twice the length of the English will not fit the button it sits in.\n" +
    "2. Keep financial acronyms in English: RSI, MACD, P/E, P/B, ROE, ROA, EBITDA, " +
    "FCF, DCF, ETF, AI. They are the same in every market.\n" +
    "3. Never translate numbers, currency symbols or ticker symbols.\n" +
    "4. Preserve leading and trailing spaces exactly — some labels are " +
    "concatenated with a value after them.\n" +
    "5. Use the vocabulary an investor in that market actually reads on a " +
    "broker's screen, not a literal word-for-word rendering.";

  const res = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model: MODEL,
      temperature: 0.1,
      response_format: { type: "json_object" },
      messages: [
        { role: "system", content: system },
        { role: "user", content: JSON.stringify(keys) },
      ],
    }),
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  const body = await res.json();
  return JSON.parse(body.choices[0].message.content);
}

async function main() {
  const langs = process.argv.slice(2);
  if (!langs.length) {
    console.error("usage: node scripts/translate-ui.mjs <lang> [lang...]");
    process.exit(1);
  }

  const keys = [...collectKeys()].sort();
  console.log(`${keys.length} UI strings found in the source`);

  // strings.ts is TypeScript; Node cannot import it directly. esbuild is
  // already a dependency of vite, so transpile to a temp module and load that
  // rather than parsing the file with a regex.
  const { execFileSync } = await import("node:child_process");
  const tmp = path.join(fs.mkdtempSync("/tmp/i18n-"), "strings.mjs");
  execFileSync("npx", ["esbuild", STRINGS, "--format=esm", `--outfile=${tmp}`,
                       "--log-level=error"], { stdio: "inherit" });
  const { UI_STRINGS: table } = await import(tmp);

  for (const lang of langs) {
    const existing = table[lang] ?? {};
    const missing = keys.filter((k) => !existing[k]);
    console.log(`${lang}: ${keys.length - missing.length} present, ${missing.length} missing`);
    if (!missing.length) continue;

    const out = { ...existing };
    // Batched: one request per 60 labels keeps each response small enough to
    // stay valid JSON, and a failed batch costs 60 strings rather than all.
    for (let i = 0; i < missing.length; i += 60) {
      const batch = missing.slice(i, i + 60);
      process.stdout.write(`  ${lang}: ${i + 1}-${i + batch.length}… `);
      try {
        Object.assign(out, await translateBatch(batch, lang));
        console.log("ok");
      } catch (e) {
        console.log(`failed (${e.message.slice(0, 60)}) — these stay English`);
      }
    }
    table[lang] = Object.fromEntries(Object.entries(out).sort());
  }

  const header = fs.readFileSync(STRINGS, "utf8").split("export const UI_STRINGS")[0];
  fs.writeFileSync(
    STRINGS,
    `${header}export const UI_STRINGS: StringTable = ${JSON.stringify(table, null, 2)};\n`
  );
  console.log(`\nwrote ${STRINGS}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
