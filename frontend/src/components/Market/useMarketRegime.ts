/**
 * The market regime, fetched once per app session and shared.
 *
 * Every recommendation card asks whether the market is weak; one request for
 * the whole list, not one per card. Refreshed after an hour, since the
 * reading changes once a day.
 */
import { useEffect, useState } from "react";
import { marketApi, type MarketRegimeReading } from "../../api/client";

let cached: { at: number; value: MarketRegimeReading | null } | null = null;
let inflight: Promise<MarketRegimeReading | null> | null = null;

function load(): Promise<MarketRegimeReading | null> {
  if (cached && Date.now() - cached.at < 3600_000) return Promise.resolve(cached.value);
  if (!inflight) {
    inflight = marketApi
      .getRegime()
      .then((r) => r.current)
      .catch(() => null)
      .then((value) => {
        cached = { at: Date.now(), value };
        inflight = null;
        return value;
      });
  }
  return inflight;
}

export function useMarketRegime(): MarketRegimeReading | null | undefined {
  const [value, setValue] = useState<MarketRegimeReading | null | undefined>(cached?.value);
  useEffect(() => {
    let alive = true;
    load().then((v) => alive && setValue(v));
    return () => {
      alive = false;
    };
  }, []);
  return value;
}
