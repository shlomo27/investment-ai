/**
 * The market regime, fetched once per app session and shared.
 *
 * Every recommendation card asks whether the market is weak; one request for
 * the whole list, not one per card. Refreshed after an hour, since the
 * reading changes once a day.
 */
import { useEffect, useState } from "react";
import { marketApi, type MarketRegimeReading } from "../../api/client";

type Both = { current: MarketRegimeReading | null; latest: MarketRegimeReading | null };
let cached: { at: number; value: Both } | null = null;
let inflight: Promise<Both> | null = null;

function load(): Promise<Both> {
  if (cached && Date.now() - cached.at < 3600_000) return Promise.resolve(cached.value);
  if (!inflight) {
    inflight = marketApi
      .getRegime()
      .then((r: any) => ({ current: r.current ?? null, latest: r.latest ?? null }))
      .catch(() => ({ current: null, latest: null }))
      .then((value) => {
        cached = { at: Date.now(), value };
        inflight = null;
        return value;
      });
  }
  return inflight;
}

function useBoth(): Both | undefined {
  const [value, setValue] = useState<Both | undefined>(cached?.value);
  useEffect(() => {
    let alive = true;
    load().then((v) => alive && setValue(v));
    return () => {
      alive = false;
    };
  }, []);
  return value;
}

/** The confirmed regime (the one users were alerted about). */
export function useMarketRegime(): MarketRegimeReading | null | undefined {
  const v = useBoth();
  return v === undefined ? undefined : v.current;
}

/** The newest reading, which may point to a regime not yet confirmed. */
export function useLatestMarketReading(): MarketRegimeReading | null | undefined {
  const v = useBoth();
  return v === undefined ? undefined : v.latest;
}
