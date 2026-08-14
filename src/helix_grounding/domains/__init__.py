"""
Domain adapters — build a GroundTruth from real source data.

The core library is domain-agnostic on purpose. Everything that knows
what a "component" or a "budget" is lives here, so adding a new vertical
means adding a file, not editing the verifier.
"""

from .bom import ground_truth_for_bom

__all__ = ["ground_truth_for_bom"]
