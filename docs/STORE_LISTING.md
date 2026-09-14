# Store listing pack

Copy, assets and answers for the App Store and Google Play submissions.

Everything here is a draft to paste, not final: **the listing is a public
marketing statement by a licensed investment advisor.** Whatever a securities
lawyer says about `/terms.html` applies to this text too — the store page is
read by more people than the terms are, and regulators look at it first.

---

## The one rule that shapes all of this copy

**Never promise performance.** No "beat the market", no returns, no win rates,
no "make money". Both stores reject financial apps over this, and in Israel it
is a regulatory exposure far more expensive than a rejection.

Describe the *mechanism*, not the *outcome*: what the system analyses, how
quickly it tells you, what you see. That is both safer and more accurate —
it's what the product actually does.

---

## Names

| Field | Value | Limit |
|---|---|---|
| App name (both stores) | `Investment AI` | 30 (Apple) / 30 (Play) |
| Apple subtitle | `ניתוח מניות והתראות בזמן אמת` | 30 |
| Play short description | `ניתוח מניות מבוסס AI והתראות על שינוי בסיגנל` | 80 |

The bundle id — `com.investmentai.app` — cannot change after the first
submission. Confirm it before submitting.

---

## Description — Hebrew

```
Investment AI סורקת מאות מניות אמריקאיות ומציגה ניתוח ממוכן שמחבר בין שלושה
מקורות: הדוחות הכספיים, החדשות, והאינדיקטורים הטכניים.

מה המערכת עושה

• מנתחת דוחות כספיים, חדשות וסנטימנט ברשתות החברתיות
• מחשבת אינדיקטורים טכניים ומזהה מתי הסיגנל משתנה
• שולחת התראה כשמניה שאתה עוקב אחריה מגיעה לנקודת כניסה
• מציגה מחיר יעד, סטופ לוס ורמת ביטחון לכל ניתוח
• מסבירה את ההיגיון מאחורי כל מסקנה, לא רק את השורה התחתונה

התראות שמגיעות בזמן

הניתוח הטכני רץ כל 30 דקות. כשהסיגנל של מניה שאתה עוקב אחריה משתנה, ההתראה
מגיעה אליך מיד — לא בסוף היום.

התוכנית החינמית

• מעקב אחרי 2 מניות
• 5 ההמלצות בעלות רמת הביטחון הגבוהה ביותר
• התראות מלאות על המניות שאתה עוקב אחריהן
• ניתוח טכני מלא

מנוי

• מעקב אחרי מניות ללא הגבלה
• כל ההמלצות החיות
• הניתוח הכלכלי המלא ונימוקי ועדת ההשקעות

חשוב לדעת

המערכת מספקת מידע וניתוח ממוכן בלבד ואינה מהווה ייעוץ השקעות אישי. הניתוח
זהה לכל המשתמשים ואינו מותאם לנסיבותיך האישיות. מסחר בניירות ערך כרוך בסיכון
להפסד, לרבות אובדן מלוא ההשקעה. תשואות העבר אינן מעידות על תשואות עתידיות.
המערכת אינה מבצעת פעולות מסחר ואינה מחוברת לחשבון המסחר שלך.

תנאי שימוש: https://<domain>/terms.html
מדיניות פרטיות: https://<domain>/privacy.html
```

## Description — English

```
Investment AI scans hundreds of US stocks and presents automated analysis
that connects three sources: financial filings, news, and technical
indicators.

What it does

• Analyses financial statements, news and social sentiment
• Computes technical indicators and detects when a signal changes
• Alerts you when a stock you follow reaches an entry point
• Shows a target price, stop loss and confidence level for every analysis
• Explains the reasoning behind each conclusion, not just the verdict

Alerts that arrive in time

Technical analysis runs every 30 minutes. When the signal changes on a stock
you follow, the alert reaches you immediately — not at the end of the day.

Free plan

• Follow 2 stocks
• The 5 highest-confidence recommendations
• Full alerts on the stocks you follow
• Complete technical analysis

Subscription

• Follow unlimited stocks
• Every live recommendation
• Full fundamental analysis and investment committee reasoning

Important

This service provides automated information and analysis only. It is not
personal investment advice. The analysis is identical for every user and is
not tailored to your circumstances. Trading securities carries risk of loss,
including your entire investment. Past performance does not indicate future
results. The app places no trades and is not connected to your brokerage
account.

Terms: https://<domain>/terms.html
Privacy: https://<domain>/privacy.html
```

---

## Keywords (Apple, 100 characters, comma-separated, no spaces)

```
מניות,בורסה,השקעות,ניתוח,מסחר,stocks,trading,analysis,alerts,portfolio
```

Do not repeat the app name — Apple indexes it already, and the space is
better spent. Avoid competitor names; it is a rejection reason.

---

## Screenshots

Take these from a **real device or simulator**, signed into a demo account
with populated data. Empty states look broken and reviewers judge on them.

**Order matters — most people never scroll past the second one.**

| # | Screen | Caption (HE) | Caption (EN) |
|---|---|---|---|
| 1 | Recommendations feed | ניתוח של מאות מניות במקום אחד | Hundreds of stocks, analysed |
| 2 | Push alert on lock screen | התראה ברגע שהסיגנל משתנה | Alerted the moment the signal turns |
| 3 | Research report | הנימוק המלא מאחורי כל מסקנה | The full reasoning behind every call |
| 4 | Technical analysis + chart | אינדיקטורים טכניים, מחושבים כל 30 דקות | Technical indicators, every 30 minutes |
| 5 | Watchlist with badges | המניות שלך, עם הסיגנל הנוכחי | Your stocks, with the current signal |

Sizes: Apple requires one set for the largest iPhone class and, if iPad is
supported, one for the largest iPad. Google Play requires a phone set plus
7" and 10" tablet sets. **Confirm the exact pixel dimensions in App Store
Connect and the Play Console at submission time** — Apple revises the
required device classes most years, and a stale size is rejected at upload.

A caption must not promise a result. "Alerted the moment the signal turns"
is a mechanism; "Never miss a winner" is a performance claim.

---

## Reviewer notes — App Store Connect

This field decides the review for a financial app. Fill it properly.

```
DEMO ACCOUNT
Email:    reviewer@<demo-domain>
Password: <generated>
This account is provisioned as PRO so the full feature set is reachable.

ABOUT THIS APP
Investment AI is an informational stock analysis tool. It executes no
trades, holds no customer funds or securities, and is not connected to any
brokerage account. It has no in-app trading capability of any kind.

REGULATORY
The operator holds an Israeli investment advice licence
(licence number: <number>, Israel Securities Authority).
The service publishes general automated analysis that is identical for all
users. It does not provide personal investment advice and performs no
suitability assessment.

SUBSCRIPTION
One auto-renewable subscription sold through In-App Purchase. There is no
alternative payment route in the app and no link to one. Restore Purchases
is on the paywall screen and in Settings.

ACCOUNT DELETION
Settings → Delete account. Deletion is immediate and permanent. A public
page describing it is at https://<domain>/account-deletion.html

PUSH NOTIFICATIONS
Alerts fire when the technical signal changes on a stock the user follows.
To see one during review: open the Recommendations tab, pick any stock whose
badge reads BUY NOW, and add it to the watchlist. A notification arrives
within seconds confirming it is at an entry point.
```

That last line matters, and it has to be precise. Following a stock only
notifies immediately when its signal is **actionable right now** — a stock
sitting in WAIT is deliberately silent, because the feed card already shows
its state and the transition alert will arrive when it turns. A reviewer told
simply to "add a stock" could pick a WAIT one, see nothing, and conclude push
notifications do not work.

A reviewer who cannot trigger the app's central feature within a minute will
either reject it under guideline 4.2 or approve it without seeing what the app
does — and the first is likelier.

---

## Apple privacy labels

Answer from `/privacy.html` section 2. Summary of the truthful answers:

| Question | Answer |
|---|---|
| Data used to track you | **No** — there is no advertising or cross-app tracking |
| Data linked to you | Contact info (name, email, phone), User content (watchlist, positions), Identifiers (push token) |
| Data not linked to you | Diagnostics (error logs) |
| Third-party advertising | None |

The honest "No" on tracking is worth stating clearly: it removes the App
Tracking Transparency prompt entirely, which is one less thing to implement
and one less reason to be rejected.

## Play Data Safety

Same source. Declare: data is encrypted in transit; users can request
deletion; the deletion URL is `https://<domain>/account-deletion.html`.

Play also has a **Financial features** declaration. Select the investment
category and be ready to upload the licence — have the document as a PDF
before starting the form, not after.

---

## Age rating

**17+ / Mature.** Both stores have a rating category covering financial
content. Rating the app lower to widen the audience invites a re-review, and
the terms already state the service is for adults.

---

## Before you press submit

- [ ] Bundle id is final
- [ ] `/privacy.html`, `/terms.html`, `/account-deletion.html` load on the
      production domain
- [ ] Lawyer has reviewed the terms and this listing text
- [ ] ISA correspondence resolved
- [ ] Demo account created, PRO, and verified working from a clean install
- [ ] Push notification tested end to end on a real device
- [ ] Purchase tested in sandbox, including Restore on a second device
- [ ] Account deletion tested — and confirmed the data is actually gone
- [ ] No purchase button or payment link anywhere in the web build
