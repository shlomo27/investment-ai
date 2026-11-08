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

  Trend warning. A BUY in a clear downtrend, or a SELL in a clear uptrend,
  goes against the trend. This used to BLOCK the signal (held at WAIT until
  the price crossed its 20-day average). A month of outcomes said the block
  was wrong: of the buys it held back, 81% had risen a month later, by 10.5%
  on average and 12.9% more than the S&P 500, while the sells it held back
  went on to fall 10%. So the signal now stands, and the trend is reported
  as a warning — on the alert, the card and the research page — and kept
  in each alert's record, so whether going against the trend pays is still
  measured.
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
) -> Tuple[str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Return (signal, strength, gate, trend_warning).

    `gate` describes the hysteresis rule that changed the signal, or is None
    when the raw reading stands. `trend_warning` is set when the final signal
    goes against a clear trend; it never changes the signal."""
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

    # 2. Trend warning — reported, not enforced.
    warning: Optional[Dict[str, Any]] = None
    if price:
        below_long = bool(ma_50 and ma_200 and price < ma_50 and price < ma_200)
        above_long = bool(ma_50 and ma_200 and price > ma_50 and price > ma_200)
        downtrend = wyckoff == "MARKDOWN" or below_long
        uptrend = wyckoff == "MARKUP" or above_long
        if signal in BUY_SIDE and downtrend and not (ma_20 and price > ma_20):
            warning = {"rule": "DOWNTREND", "against": signal,
                       "ma_20": round(ma_20, 2) if ma_20 else None}
        elif signal in SELL_SIDE and uptrend and not (ma_20 and price < ma_20):
            warning = {"rule": "UPTREND", "against": signal,
                       "ma_20": round(ma_20, 2) if ma_20 else None}

    return signal, strength, gate, warning
