/**
 * Mobile layout check — renders the app at phone size and fails on anything
 * that spills outside the viewport.
 *
 * Written because the phone screenshot showed the desktop sidebar eating a
 * sixth of the width and the sort control pushed off the edge entirely. The
 * page-level `overflow-x: hidden` in index.css stops the whole layout being
 * draggable sideways, but it also HIDES elements that overflow — so measuring
 * document.scrollWidth proves nothing. This walks every element instead and
 * reports any whose box leaves the viewport: content the user can neither see
 * nor tap.
 *
 * Run it before taking App Store screenshots.
 *
 *   npm run build && npx vite preview --port 4173 &
 *   npm i --no-save playwright
 *   node scripts/mobile-check.mjs
 *
 * The API is stubbed, so no backend is needed.
 */
import { chromium, devices } from 'playwright';

const BASE = 'http://127.0.0.1:4173';

const user = {
  id: 1, email: 'demo@test.co', full_name: 'שלמה', phone: '+972500000000',
  risk_profile: 'PASSIVE', risk_score: 50, cash_balance: 0,
  max_single_asset_exposure: 0.03, investment_type: 'BOTH',
  allows_volatile: true, allows_leveraged: false, allows_short: true,
  is_active: true, is_onboarded: true, is_admin: true, preferred_language: 'he',
  notification_email: true, notification_sms: false, notification_push: true,
  alert_frequency: 'REALTIME', totp_enabled: false, telegram_linked: false,
  created_at: '2026-01-01T00:00:00Z',
  subscription_tier: 'FREE', is_pro: false,
  watchlist_limit: 2, recommendation_limit: 5,
};

const rec = (id, symbol, name, type, conf, price, target, stop) => ({
  id, symbol, recommendation_type: type, status: 'APPROVED',
  confidence_score: conf, target_price: target, stop_loss: stop,
  current_price_at_recommendation: price,
  fundamental_analysis: { thesis: 'תזה לדוגמה', direction_bias: 'LONG' },
  fundamental_notes: null, sentiment_data: null,
  senior_review_notes: 'ועדת ההשקעות מאשרת את הפוזיציה בהקצאה מופחתת של 1.5% בלבד בשל חסרי נתונים.',
  senior_notes: null,
  technical_analysis: { timing_signal: 'BUY_NOW', technical_score: 72, current_price: price },
  risk_factors: [], expected_return_pct: 12.4,
  trigger_type: null, trigger_details: null,
  asset_name: name, sector: 'Technology', risk_level: 'HIGH', beta: 1.36,
  reasoning_locked: false,
  created_at: '2026-09-14T09:00:00Z', approved_at: '2026-09-14T09:00:00Z',
  presented_at: null,
});

const recs = [
  rec(1, 'HOG', 'Harley-Davidson', 'SELL', 55, 27.59, 21.50, 32.50),
  rec(2, 'APP', 'AppLovin', 'BUY', 55, 320.56, 400.00, 275.00),
  rec(3, 'NVDA', 'NVIDIA Corporation', 'STRONG_BUY', 78, 184.20, 240.00, 160.00),
  rec(4, 'VRTX', 'Vertex Pharmaceuticals', 'BUY', 64, 412.10, 480.00, 372.00),
];

const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const ctx = await browser.newContext({ ...devices['iPhone 14 Pro Max'] });

await ctx.route('**/api/v1/**', async (route) => {
  const url = route.request().url();
  if (url.includes('/auth/me')) return route.fulfill(json(user));
  if (url.includes('/recommendations/hidden-count'))
    return route.fulfill(json({ hidden_total: 0, hidden_short: 0, hidden_volatile: 0, locked_by_tier: 23, tier: 'FREE', recommendation_limit: 5 }));
  if (url.includes('/recommendations/unread-count')) return route.fulfill(json({ count: 9 }));
  if (url.includes('/recommendations/inbox')) return route.fulfill(json([]));
  if (url.includes('/recommendations/scan-activity')) return route.fulfill(json({ items: [], totals: {} }));
  if (url.match(/\/recommendations\/?(\?|$)/)) return route.fulfill(json(recs));
  if (url.includes('/watchlist')) return route.fulfill(json([]));
  if (url.includes('/portfolio')) return route.fulfill(json([]));
  if (url.includes('/billing/status'))
    return route.fulfill(json({ tier: 'FREE', is_pro: false, expires_at: null, source: null, watchlist_limit: 2, recommendation_limit: 5, full_research: false }));
  return route.fulfill(json([]));
});

const page = await ctx.newPage();
await page.addInitScript(() => {
  localStorage.setItem('access_token', 'stub');
  localStorage.setItem('refresh_token', 'stub');
});

await page.goto(`${BASE}/recommendations`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1500);

// Anything in the header overlapping or clipped?
const header = await page.evaluate(() => {
  const h = document.querySelector('header');
  if (!h) return null;
  const hr = h.getBoundingClientRect();
  return {
    headerBox: [Math.round(hr.left), Math.round(hr.top), Math.round(hr.width), Math.round(hr.height)],
    children: [...h.querySelectorAll('*')].filter(e => {
      const r = e.getBoundingClientRect(); return r.width && r.height;
    }).map(e => {
      const r = e.getBoundingClientRect();
      return { tag: e.tagName.toLowerCase(), text: (e.textContent||'').trim().slice(0,18),
               box: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
               clipped: r.bottom > hr.bottom + 1 || r.top < hr.top - 1 };
    }),
  };
});
console.log('HEADER:', JSON.stringify(header, null, 1));

// overflow-x:hidden on <body> stops the PAGE dragging sideways, but it also
// hides elements that spill — so measuring the document proves nothing. Walk
// every element and report anything whose box leaves the viewport: that is
// content the user can neither see nor tap.
const metrics = await page.evaluate(() => {
  const vw = document.documentElement.clientWidth;
  const bad = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (getComputedStyle(el).position === 'fixed') continue;
    if (r.right > vw + 1 || r.left < -1) {
      bad.push({
        tag: el.tagName.toLowerCase(),
        text: (el.textContent || '').trim().slice(0, 32),
        left: Math.round(r.left), right: Math.round(r.right),
      });
    }
  }
  return {
    viewport: vw,
    sidebarVisible: !!document.querySelector('aside') &&
      getComputedStyle(document.querySelector('aside')).display !== 'none',
    bottomNav: !!document.querySelector('nav[class*="fixed"]'),
    offscreen: bad.slice(0, 8),
    offscreenCount: bad.length,
  };
});
console.log(JSON.stringify(metrics, null, 2));
console.log(metrics.offscreenCount === 0
  ? 'PASS: nothing spills outside the viewport'
  : `FAIL: ${metrics.offscreenCount} element(s) off-screen`);

await page.screenshot({ path: 'mobile-shots/m-signals.png' });

// The More sheet — the only route to Portfolio/Orders/Settings on a phone.
await page.click('nav button:has-text("עוד")');
await page.waitForTimeout(400);
await page.screenshot({ path: 'mobile-shots/m-more.png' });
await page.keyboard.press('Escape');

// Every authenticated route, not a sample. /fund was skipped the first time
// and was exactly where the next cut-off row turned up.
const ROUTES = [
  ['/fund', 'm-fund'],
  ['/watchlist', 'm-watchlist'],
  ['/portfolio', 'm-portfolio'],
  ['/orders', 'm-orders'],
  ['/performance', 'm-performance'],
  ['/dashboard', 'm-dashboard'],
  ['/settings', 'm-settings'],
];
for (const [route, name] of ROUTES) {
  await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  const off = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const bad = [];
    // An element inside a horizontally scrollable ancestor is reachable by
    // swiping, so it is not a defect — only content with no way to scroll to
    // it counts.
    const scrollable = (el) => {
      for (let p = el.parentElement; p; p = p.parentElement) {
        const ov = getComputedStyle(p).overflowX;
        if ((ov === 'auto' || ov === 'scroll') && p.scrollWidth > p.clientWidth + 1) return true;
      }
      return false;
    };
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      if (getComputedStyle(el).position === 'fixed') continue;
      if (r.right > vw + 1 || r.left < -1) {
        if (!scrollable(el)) bad.push((el.textContent || '').trim().slice(0, 28));
      }
    }
    return bad;
  });
  console.log(`${route}: ${off.length === 0 ? 'PASS' : `FAIL — unreachable: ${JSON.stringify(off.slice(0,4))}`}`);
  await page.screenshot({ path: `/tmp/claude-0/${name}.png` });
}

await browser.close();
