"""
HELIX CORE — Component Alternatives Lookup Tool

THIS IS MOCK DATA, NOT A REAL DISTRIBUTOR CONNECTION. Clearly labeled as
such throughout -- this file demonstrates the tool-use pattern that makes
specific-part recommendations trustworthy instead of hallucinated, using
a small hand-built dataset standing in for what a real integration
(Octopart, DigiKey, or Mouser API) would provide. A real integration
needs the owner's own API credentials, same handling rules as the LLM
API key (env variable, never pasted in chat) -- not built here since no
such account/key exists yet.

Why this exists: an LLM asked to "suggest an alternative part" will
invent a plausible-sounding part number and specs from pattern-matching,
not real knowledge of current stock/pricing -- this is the same failure
mode as the "onboard RAM" fabrication caught in the BME280 example
(D-033/chat). Grounding the recommendation in an actual looked-up
alternative, real or mock, is what prevents that.
"""

from dataclasses import dataclass


@dataclass
class AlternativePart:
    manufacturer: str
    manufacturer_part_number: str
    cost_usd: float
    lead_time_days: int
    note: str


# MOCK DATASET -- a real integration replaces this dict with an actual
# API call. Kept intentionally small and clearly synthetic.
_MOCK_ALTERNATIVES_DB = {
    "BME280": [
        AlternativePart(
            manufacturer="Bosch", manufacturer_part_number="BME680",
            cost_usd=3.10, lead_time_days=14,
            note="Adds gas/VOC sensing on top of temp/humidity/pressure -- "
                 "pin-compatible footprint, higher cost, much shorter lead time.",
        ),
        AlternativePart(
            manufacturer="Sensirion", manufacturer_part_number="SHT31-DIS-B",
            cost_usd=1.95, lead_time_days=21,
            note="Temp/humidity only, no pressure sensing -- cheaper and "
                 "faster to source if pressure data isn't actually needed.",
        ),
    ],
}


def lookup_alternatives(manufacturer_part_number: str) -> list:
    """Returns real (here: mock) alternative parts for a given MPN, or an
    empty list if none are known -- an empty list is the honest answer
    when there's nothing grounded to offer, not a prompt to let the LLM
    guess instead.

    Lookup is case-insensitive. Real BOMs are typed by hand and exported from
    a dozen different tools, so "bme280" and "BME280" both arrive; an exact
    match silently returned nothing for the lowercase form, which reads as
    "no alternatives exist" rather than "you spelled it differently."
    """
    if not manufacturer_part_number:
        return []
    return _MOCK_ALTERNATIVES_DB.get(manufacturer_part_number.strip().upper(), [])
