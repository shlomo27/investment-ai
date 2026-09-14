/**
 * Generates the icon sources @capacitor/assets rasterises into every store size.
 *
 * Three files rather than one, because the two platforms crop differently:
 *
 *   icon.png            iOS + web. Opaque, full-bleed, mark at 82%. Apple
 *                       rejects an alpha channel and applies its own squircle
 *                       mask, so any rounding baked in here would show as a
 *                       second rounded square inset inside the real one.
 *
 *   icon-foreground.png Android adaptive. Transparent, mark at 58%, because
 *                       the launcher may mask this layer to a circle and only
 *                       the middle ~66% is guaranteed visible. At full size
 *                       the green terminal node — the focal point of the mark —
 *                       falls outside that circle and gets sliced off.
 *   icon-background.png Android adaptive, the flat field behind it.
 *
 * Run: node assets/build-icons.mjs
 */
import sharp from "sharp";

const BG_DARK = "#030712";

const mark = (scale) => `
  <g transform="translate(512,512) scale(${scale}) translate(-512,-512)">
    <g fill="#1e293b">
      <rect x="196" y="606" width="78" height="200" rx="18"/>
      <rect x="316" y="536" width="78" height="270" rx="18"/>
      <rect x="436" y="580" width="78" height="226" rx="18"/>
      <rect x="556" y="452" width="78" height="354" rx="18"/>
      <rect x="676" y="498" width="78" height="308" rx="18"/>
    </g>
    <polyline points="235,652 355,566 475,610 595,410 715,300"
      fill="none" stroke="url(#line)" stroke-width="46"
      stroke-linecap="round" stroke-linejoin="round"/>
    <g fill="#e2e8f0">
      <circle cx="235" cy="652" r="26"/>
      <circle cx="355" cy="566" r="26"/>
      <circle cx="475" cy="610" r="26"/>
      <circle cx="595" cy="410" r="26"/>
    </g>
    <circle cx="715" cy="300" r="52" fill="${BG_DARK}"/>
    <circle cx="715" cy="300" r="52" fill="none" stroke="#22c55e" stroke-width="26"/>
  </g>`;

const defs = `
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0b1220"/>
      <stop offset="100%" stop-color="${BG_DARK}"/>
    </linearGradient>
    <linearGradient id="line" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="55%" stop-color="#3b82f6"/>
      <stop offset="100%" stop-color="#22c55e"/>
    </linearGradient>
  </defs>`;

const doc = (body) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">${defs}${body}</svg>`;

// The foreground layer sits on a transparent field; the node's inner fill has
// to stay opaque or the launcher background shows through the ring.
const files = [
  ["assets/icon.png", doc(`<rect width="1024" height="1024" fill="url(#bg)"/>${mark(0.82)}`), true],
  ["assets/icon-foreground.png", doc(mark(0.58)), false],
  ["assets/icon-background.png", doc(`<rect width="1024" height="1024" fill="url(#bg)"/>`), true],
  // Splash is 2732² so it survives any orientation on the largest iPad.
  ["assets/splash.png", doc(`<rect width="1024" height="1024" fill="url(#bg)"/>${mark(0.34)}`), true],
];

for (const [path, svg, flatten] of files) {
  let img = sharp(Buffer.from(svg)).resize(
    path.includes("splash") ? 2732 : 1024,
    path.includes("splash") ? 2732 : 1024
  );
  if (flatten) img = img.flatten({ background: BG_DARK });
  const info = await img.png().toFile(path);
  console.log(path, `${info.width}x${info.height}`, `${info.channels}ch`);
}
