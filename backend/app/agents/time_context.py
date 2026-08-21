"""
Current-date context shared by every analyst agent.

Without it the models anchor on their training cutoff. That is not a subtle
degradation: the catalyst protocol asks for events "within 18 months from
today", so a model that does not know today happily dates a catalyst to a
conference or a guidance window that has ALREADY PASSED, and presents it as
forward-looking. A recommendation built on a spent catalyst is simply wrong.

Injected into the system prompt of every agent that reasons about time.
"""
from datetime import datetime, timezone
from typing import Optional


def current_date_block(as_of_iso: Optional[str] = None) -> str:
    """Today's date plus the rules that make the model use it.

    as_of_iso: when the market data was actually fetched, so the model can tell
    a current figure from one carried over from an earlier run.
    """
    now = datetime.now(timezone.utc)
    today = now.strftime("%d %B %Y")
    quarter = f"Q{(now.month - 1) // 3 + 1} {now.year}"

    freshness = ""
    if as_of_iso:
        freshness = f"\nMarket data in this prompt was fetched: {as_of_iso}"

    return f"""

══════════════════════════════════════════════
CURRENT DATE — READ THIS BEFORE REASONING ABOUT ANY TIMELINE
══════════════════════════════════════════════
TODAY IS {today}. The current quarter is {quarter}.{freshness}

Your training data ends well before today. Anything you "remember" about this
company may be out of date, and you must not present it as current.

BINDING RULES:
✗ NEVER cite a catalyst dated before {today}. An event that has already
  happened is history, not a catalyst — if you are unsure whether it has
  occurred, say so explicitly instead of assuming it is upcoming.
✗ NEVER describe a past year's guidance, targets or conference as forward
  looking. "By end of {now.year - 1}" is the PAST.
✗ NEVER state a figure from memory as if it were current. Use only the
  numbers supplied in this prompt; if a number you need is not here, say it
  is unavailable.
✓ Every date you write must be explicit and must fall AFTER {today}.
✓ "Within 18 months" means between {today} and {now.year + 1}-{now.month:02d}.
✓ When your knowledge and the supplied data disagree, THE SUPPLIED DATA WINS.
"""
