/**
 * Routing a notification tap to a screen.
 *
 * Two awkward facts make this its own module rather than a line in App.tsx:
 *
 *  1. App renders <Router> inside itself, so App cannot call useNavigate —
 *     the hook only exists below the router.
 *  2. Tapping a notification on a cold-started phone fires the handler while
 *     the app is still booting. The router does not exist yet, and a naive
 *     navigate() call is simply lost: the user taps "BMRN crossed its entry"
 *     and lands on the dashboard, which looks exactly like the app ignoring
 *     them.
 *
 * So taps are buffered until the router announces itself, then flushed.
 */

type Navigate = (path: string) => void;

let navigate: Navigate | null = null;
let pending: string | null = null;

/** Called by the bridge component once the router is mounted. */
export function setPushNavigator(fn: Navigate | null): void {
  navigate = fn;
  if (fn && pending) {
    const path = pending;
    pending = null;
    fn(path);
  }
}

/**
 * Navigate now if the router is up, otherwise hold the destination until
 * it is. Only the most recent tap is kept — if several notifications are
 * tapped before boot finishes, the last one is the one the user meant.
 */
export function pushNavigate(path: string): void {
  if (navigate) navigate(path);
  else pending = path;
}
