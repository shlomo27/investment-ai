"""What each subscription tier is allowed to do.

One module owns every limit. The alternative — a number written into the
watchlist endpoint, another into the recommendations endpoint, a third into
the alert dispatcher — is how a paywall ends up leaking: a free account that
cannot add a third stock through the UI but receives alerts for twenty
because the notification path never learned about tiers.

Every limit here is enforced **server-side**. The app also hides what a free
account cannot use, but that is presentation only: a client is something the
user controls, and on a subscription boundary it will eventually be edited.
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoids a circular import at runtime
    from app.db.models.user import User


@dataclass(frozen=True)
class Entitlements:
    """The resolved limits for one account."""

    tier: str

    #: How many stocks may be followed. None means unlimited.
    watchlist_limit: int | None

    #: How many live recommendations are visible in the feed. None means all.
    #: A free account sees the strongest few rather than a random slice —
    #: see visible_recommendations() for the ordering.
    recommendation_limit: int | None

    #: Whether alerts are delivered for followed stocks at all.
    alerts_enabled: bool

    #: Whether the full research report (fundamentals, committee reasoning,
    #: news analysis) opens, or only the headline signal.
    full_research: bool

    @property
    def is_unlimited(self) -> bool:
        return self.watchlist_limit is None and self.recommendation_limit is None


# The free tier is deliberately usable rather than crippled: someone who
# follows two stocks and gets real alerts on them has seen the product work,
# which is what makes the upgrade worth buying. It is affordable precisely
# because analyses are shared across all accounts — a free user adds database
# rows and push messages, not AI spend.
FREE = Entitlements(
    tier="FREE",
    watchlist_limit=2,
    recommendation_limit=5,
    alerts_enabled=True,
    full_research=False,
)

PRO = Entitlements(
    tier="PRO",
    watchlist_limit=None,
    recommendation_limit=None,
    alerts_enabled=True,
    full_research=True,
)


def entitlements_for(user: "User") -> Entitlements:
    """Resolve what this account may do right now.

    Admins get PRO without a subscription — they operate the system, and
    locking staff out of the product they run helps nobody.
    """
    if getattr(user, "is_admin", False):
        return PRO
    return PRO if user.is_pro else FREE
