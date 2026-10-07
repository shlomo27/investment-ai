"""Rules applied to the technical signal after it is scored.

The score is a sum of modules that often disagree. On BMRN in October 2026
it read 60 — exactly the BUY threshold — from an RSI of 12, a Fibonacci level
and an Elliott count (+29 between them, all saying "it has fallen a lot")
against moving averages, Wyckoff and MACD (−27, all saying "and it is still
falling"). The label followed the arithmetic, so the stock was called a buy at
$64, again at $60 and again at $56 while it fell 16% in a month, and every
small bounce around 60 sent another BUY / WAIT / BUY round to its watchers.

Two rules, both pure functions of the reading and the last confirmed signal,
so the research page and the alerts can never disagree about which applied:

  Hysteresis. A signal is entered at its threshold and left only past a
  margin: BUY at 60, back to WAIT below 55; SELL at 40, back to WAIT above 45.
  A score wobbling between 57 and 61 no longer flips the signal.

  Trend gate. In a clear downtrend, being oversold is not a reason to buy —
  oversold readings are what a downtrend produces. A BUY there is held at
  WAIT until the price closes back above its 20-day average, the first
  evidence the decline has paused. The mirror rule holds a SELL in a clear
  uptrend until the price closes below its 20-day average.
"""
from typing import Any, Dict, Optional, Tuple

BUY_SIDE = ("BUY_NOW", "STRONG_BUY")
SELL_SIDE = ("SELL_NOW", "STRONG_SELL")

#: Scores at which a held signal is finally let go.
BUY_EXIT_BELOW = 55
SELL_EXIT_ABOVE = 45


def apply_signal_gates(
    *,
    score: float,
    signal: str,
    strength: str,
    price: Optional[float],
    ma_20: Optional[float],
    ma_50: Optional[float],
    ma_200: Optional[float],
    wyckoff: Optional[str],
    prev_confirmed: Optional[str],
) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Return (signal, strength, gate). `gate` describes the rule that
    changed the signal, or is None when the raw reading stands."""
    gate: Optional[Dict[str, Any]] = None

    # 1. Hysteresis — keep the confirmed signal until the score clears the
    #    exit margin.
    if signal == "WAIT":
        if prev_confirmed in BUY_SIDE and score >= BUY_EXIT_BELOW:
            signal, strength = "BUY_NOW", "MODERATE"
            gate = {"rule": "HOLD_BUY", "exit_below": BUY_EXIT_BELOW}
        elif prev_confirmed in SELL_SIDE and score <= SELL_EXIT_ABOVE:
            signal, strength = "SELL_NOW", "MODERATE"
            gate = {"rule": "HOLD_SELL", "exit_above": SELL_EXIT_ABOVE}

    # 2. Trend gate — wins over hysteresis: a held BUY in a stock that has
    #    since entered a downtrend is exactly what must not survive.
    if price:
        below_long = bool(ma_50 and ma_200 and price < ma_50 and price < ma_200)
        above_long = bool(ma_50 and ma_200 and price > ma_50 and price > ma_200)
        downtrend = wyckoff == "MARKDOWN" or below_long
        uptrend = wyckoff == "MARKUP" or above_long

        if signal in BUY_SIDE and downtrend and not (ma_20 and price > ma_20):
            signal, strength = "WAIT", "WEAK"
            gate = {"rule": "DOWNTREND", "confirm_above": round(ma_20, 2) if ma_20 else None}
        elif signal in SELL_SIDE and uptrend and not (ma_20 and price < ma_20):
            signal, strength = "WAIT", "WEAK"
            gate = {"rule": "UPTREND", "confirm_below": round(ma_20, 2) if ma_20 else None}

    return signal, strength, gate
