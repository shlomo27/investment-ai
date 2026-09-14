# Shipping the mobile apps

The React app is wrapped with Capacitor, so iOS and Android run the same
screens, store and API client as the web build. No separate codebase.

```
frontend/
  capacitor.config.ts          appId, webDir, plugin config
  assets/build-icons.mjs       regenerates every icon/splash source
  android/                     generated native project — committed
  ios/                         generated native project — committed
  src/platform.ts              isNative() / platform()
  src/services/
    pushNotifications.ts       dispatcher: web path + platform branch
    pushNotificationsNative.ts native FCM (iOS + Android)
    pushNavigation.ts          buffers notification taps until the router mounts
codemagic.yaml                 CI: builds and uploads both stores
```

## Local commands

```bash
cd frontend
npm run mobile:sync        # build web assets + copy into both native projects
npm run mobile:android     # ...then open Android Studio
npm run mobile:ios         # ...then open Xcode (macOS only)
npm run icons              # regenerate all icon/splash sizes from the SVG source
```

`npx cap sync` must run after every web change — the native apps serve a
*copy* of `dist/`, not the live folder.

---

## The one irreversible decision

`appId` in `capacitor.config.ts` is currently **`com.investmentai.app`**.

Apple and Google key an app's identity — its reviews, installed base and
subscriptions — to this string permanently. It cannot be changed after the
first store submission. If the company domain differs, change it now, in
`capacitor.config.ts`, `android/app/build.gradle` (both `namespace` and
`applicationId`), and the iOS `PRODUCT_BUNDLE_IDENTIFIER`.

---

## Start here: the long-lead item

**D-U-N-S number.** Free, from Dun & Bradstreet, 5–14 business days. It blocks
everything else, so request it before any of the work below.

It is needed to register the developer accounts as a **company** rather than an
individual, which matters twice over:

- Google Play requires new *personal* accounts to run 12 testers for 14
  continuous days before publishing. Company accounts are exempt.
- Apple requires apps providing financial services to be submitted by the
  licensed entity. The investment advice licence is what clears this — register
  the account in the licensed entity's name and have the licence number ready.

| | Cost |
|---|---|
| Apple Developer Program | $99/year |
| Google Play Console | $25 one-time |
| Codemagic | free tier, 500 build-min/month |

---

## Firebase — the part that fails silently

Push already worked end-to-end on the web before the apps existed; the backend
(`app/services/notifications/service.py`) sends through `firebase-admin` to
`user.push_token` and does not care which platform issued the token.

Three files have to exist or push dies quietly — the app registers, receives a
token, and simply never gets a notification:

1. **`android/app/google-services.json`** — Firebase console → Project settings
   → Android app. Capacitor's `build.gradle` applies the google-services plugin
   only if this file is present, and logs a line nobody reads if it is not.
2. **`ios/App/App/GoogleService-Info.plist`** — same page, iOS app.
3. **APNs Auth Key (`.p8`)** — Apple Developer → Certificates, Identifiers &
   Profiles → Keys → new key with "Apple Push Notifications service" ticked.
   Upload it to Firebase → Project settings → Cloud Messaging → iOS app
   configuration.

**The `.p8` is the one people miss.** Without it iOS registration succeeds and
delivery never happens, with no error on either side. Download it once — Apple
will not let you download it again.

Neither Firebase file is committed. They go into Codemagic as base64 secrets:

```bash
base64 -i google-services.json        # → GOOGLE_SERVICES_JSON
base64 -i GoogleService-Info.plist    # → GOOGLE_SERVICE_INFO_PLIST
```

For local device testing, place the real files at the two paths above — both
are gitignored by Capacitor's own rules.

---

## Codemagic

Two workflows in `codemagic.yaml`: `android` (Linux, → Play internal track) and
`ios` (macOS, → TestFlight). Neither submits for public review automatically —
that stays a deliberate manual step.

Set up in the Codemagic UI before the first run:

- **Environment group `investment_ai`** — `VITE_API_URL` plus the six
  `VITE_FIREBASE_*` values, all marked secure.
- **Environment group `firebase_config`** — the two base64 blobs above.
- **`investment_ai_keystore`** — Android signing. Generate once and *keep the
  backup*: Play permanently binds the app to the first key it sees, and losing
  it means never updating the app again. (Enrolling in Play App Signing at
  upload time makes this recoverable — worth doing.)
- **App Store Connect API key** integration → used by both `ios_signing` and
  publishing.
- **Google Play service account JSON** → `GCLOUD_SERVICE_ACCOUNT_CREDENTIALS`.

`VITE_API_URL` is the setting that breaks everything invisibly if forgotten:
the app builds, installs, launches — and cannot log in, because a relative
`/api/...` resolves inside the app bundle rather than through nginx. Both
workflows fail the build deliberately when it is unset.

If an Android build produces an unsigned AAB, check that the `android_signing`
keystore is attached to the workflow — Codemagic patches signing into
`build.gradle` at build time, and silently produces an unsigned bundle if the
keystore reference is missing.

---

## Store review — where a financial app actually gets stopped

**Apple guideline 4.2, "minimum functionality".** An app that is only a website
in a window is rejected, and this is the most common outcome for a wrapper.
What we ship against it: real push notifications, native splash and status bar,
deep links that open a specific stock, offline-capable bundled assets. Adding
biometric unlock before submission would strengthen this further.

**Financial services.** Both stores screen investment apps and ask for proof of
licensing. Submit as the licensed entity and have the licence number to hand.

**Do not add in-app purchase.** Apple takes 15–30% of anything sold inside the
app. A broker who signs a contract and is then issued credentials costs
nothing — which is exactly how the demo accounts already work. Keep every
payment and sign-up flow outside the app; there must be no purchase button and
no link to one.

**Required and already in place:**

- In-app account deletion — Settings → Delete account (Apple rejects apps with
  sign-up and no in-app deletion; it is checked by hand).
- Privacy policy — `/privacy.html`, publicly reachable.
- Data deletion page — `/account-deletion.html`, for the Play Data Safety form.

**Still needed at submission time:**

- Screenshots: iPhone 6.7" and 6.5", iPad 12.9" if iPad is supported; Android
  phone and 7"/10" tablet.
- Apple privacy "nutrition labels" — answered from the privacy policy's
  section 2.
- Play Data Safety form — same source.
- A demo account for the reviewer, in the review notes. Reviewers reject apps
  they cannot sign into. Use a dedicated account, not a prospect's.
- Support URL and marketing description.

---

## Realistic timeline

| Week | |
|---|---|
| 1 | D-U-N-S request, developer accounts, Firebase project + `.p8` |
| 2 | Codemagic setup, first builds, test on real devices |
| 3 | Screenshots, store listings, privacy forms |
| 4–5 | Apple review — **assume one rejection round.** Google is usually 1–3 days |

About four to six weeks, most of it waiting rather than working.
