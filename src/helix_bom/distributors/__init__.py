"""Where parts can be looked up.

Reading, never ordering: no class here has a method that spends money, and the
base class has no such method to override.
"""

from .base import (
    Capabilities,
    Distributor,
    Lifecycle,
    Lookup,
    Offer,
    Outcome,
    PartRecord,
    PriceBreak,
    normalise_mpn,
    parse_money,
    read_lifecycle,
)
from .cache import LookupCache, default_cache_path
from .digikey import DigiKeyDistributor
from .mouser import MouserDistributor
from .offline import OfflineDistributor

__all__ = [
    "Capabilities", "Distributor", "Lifecycle", "Lookup", "Offer", "Outcome",
    "PartRecord", "PriceBreak", "normalise_mpn", "parse_money", "read_lifecycle",
    "LookupCache", "default_cache_path",
    "DigiKeyDistributor", "MouserDistributor", "OfflineDistributor",
]


def live_distributors(environment=None):
    """The real ones, in the order they should be asked.

    Mouser first only because its rate limit is the one that bites soonest, so
    a cache miss there is worth spending early while the minute budget is
    fresh. Both are asked when --compare is set.
    """
    return [MouserDistributor(environment=environment),
            DigiKeyDistributor(environment=environment)]
