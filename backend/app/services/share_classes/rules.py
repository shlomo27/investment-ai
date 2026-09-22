"""Deciding when two listings are the same investment.

Two tickers from one issuer are not automatically interchangeable, and
getting this wrong is worse than not grouping at all: presenting the
analysis of one business under the name of another is a factual error on a
financial screen, not a cosmetic one.

So the same issuer is treated as a NECESSARY condition, never a sufficient
one. Everything here exists to reject pairs that share an issuer but not an
investment:

  Tracking stocks   One issuer, separate businesses. Liberty Media ran
                    tickers tracking Formula One, the Atlanta Braves and
                    SiriusXM at once — same CIK, nothing else in common.
  Preferred shares  Fixed dividend, liquidation priority, usually no vote.
                    Behaves like a bond and moves with rates, not earnings.
  Dual-listed       Two legal companies operating under contract as one
                    (Carnival's CCL and CUK). Different domicile, different
                    dividend taxation, persistent price gap.
  Unit/warrant      SPAC units and warrants are derivatives of the common,
                    not the common.

The default answer is NO. A pair is only equivalent when nothing here
objects, which means a structure nobody anticipated is excluded rather than
silently merged.
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

#: Suffixes that mark something other than ordinary common stock. Kept as
#: patterns on the symbol because that is what data providers agree on;
#: names are inconsistent across sources.
_NON_COMMON_SUFFIX = re.compile(
    r"(?:"
    r"[.\-]P[A-Z]?$"      # BAC.PL, XYZ-PA — preferred series
    r"|[.\-]PR[A-Z]?$"    # XYZ.PRA
    r"|[.\-]W[STS]?$"     # warrants: XYZ.WS, XYZ-W
    r"|[.\-]U$"           # SPAC units
    r"|[.\-]RT$"          # rights
    r")",
    re.IGNORECASE,
)

#: Words in a security's NAME that mean it is not plain common stock.
_NON_COMMON_WORDS = (
    "preferred", "pfd", "depositary", "warrant", "right", "unit",
    "tracking", "note", "bond", "debenture", "trust preferred",
)

#: Names that mark a tracking stock even without the word "tracking".
#: These are structures where one issuer's tickers follow different
#: businesses, so a shared issuer says nothing about shared economics.
_TRACKING_HINTS = ("liberty", "series a liberty", "formula one", "braves")

#: Pairs that share an issuer but are deliberately never grouped, with the
#: reason recorded so the list can be argued with rather than trusted.
EXCEPTIONS: dict = {
    # Dual-listed company: two legal entities, different domicile and
    # dividend taxation, a persistent and real price gap.
    frozenset({"CCL", "CUK"}): "dual-listed structure — different tax treatment",
}


@dataclass(frozen=True)
class Listing:
    symbol: str
    name: str
    cik: Optional[str] = None
    last_price: Optional[float] = None
    #: Average daily volume in SHARES. Converted to money before comparing —
    #: share counts are meaningless across a 1000:1 price difference.
    avg_volume: Optional[float] = None


def is_common_stock(listing: Listing) -> bool:
    """Whether this is ordinary common stock, as opposed to preferred,
    warrants, units, rights or a tracking stock."""
    if _NON_COMMON_SUFFIX.search(listing.symbol or ""):
        return False
    name = (listing.name or "").lower()
    if any(word in name for word in _NON_COMMON_WORDS):
        return False
    if any(hint in name for hint in _TRACKING_HINTS):
        return False
    return True


def _base_name(name: str) -> str:
    """The company name with the share-class wording stripped.

    "Alphabet Inc. Class C" and "Alphabet Inc." must reduce to the same
    string; "Liberty Formula One Series A" and "Liberty Braves Series A"
    must not.
    """
    n = (name or "").lower()
    n = re.sub(r"\bclass\s+[a-z]\b", " ", n)
    n = re.sub(r"\bseries\s+[a-z]\b", " ", n)
    n = re.sub(r"\b(the|inc|inc\.|corp|corp\.|corporation|company|co|co\.|plc|ltd|ltd\.|holdings|group)\b", " ", n)
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def equivalent(a: Listing, b: Listing, *, max_price_ratio: float = 2000.0) -> bool:
    """Whether two listings are the same investment in different wrappers.

    `max_price_ratio` is deliberately loose. Berkshire's A and B shares
    differ by about 1500:1 and ARE equivalent — the B share is simply a
    fraction of the A. A price gap is therefore not evidence of different
    economics, and using it as one would reject the most famous correct pair
    there is. It only guards against a nonsensical pairing.
    """
    if not a.cik or not b.cik or a.cik != b.cik:
        return False
    if a.symbol == b.symbol:
        return False
    if frozenset({a.symbol, b.symbol}) in EXCEPTIONS:
        return False
    if not is_common_stock(a) or not is_common_stock(b):
        return False
    # Same issuer, both common — but a tracking structure gives each ticker a
    # different underlying business, and only the name reveals that.
    if _base_name(a.name) != _base_name(b.name):
        return False
    if a.last_price and b.last_price:
        hi, lo = max(a.last_price, b.last_price), min(a.last_price, b.last_price)
        if lo > 0 and hi / lo > max_price_ratio:
            return False
    return True


def choose_primary(
    listings: Sequence[Listing], *, affordable_under: float = 2000.0
) -> Optional[Listing]:
    """The listing to analyse and show, out of an equivalent group.

    Affordability comes FIRST, and that ordering is the whole point.
    Berkshire's A share is the more expensive and, by dollar volume, far
    from illiquid — but at roughly $700,000 a share almost no reader of this
    app can buy one. Ranking by liquidity alone would recommend a stock its
    audience cannot purchase.

    Among listings a reader can actually buy, the tie-break is dollar
    volume — price times shares. Ranking by share count instead would favour
    whichever listing happens to have the smaller share price, which is not
    the same thing as being easier to trade.
    """
    if not listings:
        return None

    def dollar_volume(x: Listing) -> float:
        return (x.last_price or 0) * (x.avg_volume or 0)

    affordable = [x for x in listings if (x.last_price or 0) <= affordable_under]
    pool = affordable or list(listings)
    # Symbol breaks a genuine tie so the choice is stable between runs —
    # a primary that changes on every scan would move the analysis around.
    return sorted(pool, key=lambda x: (-dollar_volume(x), x.symbol))[0]


def group_equivalents(listings: Sequence[Listing]) -> List[List[Listing]]:
    """Partition listings into groups that are the same investment.

    Singletons are included: most stocks have exactly one listing, and the
    caller should not have to special-case them.
    """
    remaining = list(listings)
    groups: List[List[Listing]] = []
    while remaining:
        head = remaining.pop(0)
        group = [head]
        rest = []
        for other in remaining:
            (group if equivalent(head, other) else rest).append(other)
        remaining = rest
        groups.append(group)
    return groups
