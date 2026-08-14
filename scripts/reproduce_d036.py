"""
Reproduce the two errors a live model actually made, and show which defence
stops each one.

This is not a hypothetical. On 2026-07-15 a full-pipeline run over an 18-item
BOM produced synthesis text with two real mistakes (DECISION_LOG.md D-036).
They failed in different ways, and that difference is the whole reason this
system has two layers instead of one.

Run it:  python scripts/reproduce_d036.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from helix_bom.agent import Component, DesignConstraints  # noqa: E402
from helix_bom.components import lookup_alternatives      # noqa: E402
from helix_grounding import Verifier                      # noqa: E402
from helix_grounding.domains.bom import ground_truth_for_bom  # noqa: E402


def rule(title: str) -> None:
    print(f"\n{title}\n{'=' * len(title)}")


# The relevant slice of the BOM from that run.
COMPONENTS = [
    Component("ESP32-S3 module", 3.20, 25.5, 18.0, 3.1, 0.24, "compute",
              quantity=1, manufacturer="Espressif",
              manufacturer_part_number="ESP32-S3-WROOM-1", lead_time_days=21),
    Component("BME280 sensor", 2.40, 2.5, 2.5, 0.93, 0.004, "sensor",
              quantity=1, manufacturer="Bosch",
              manufacturer_part_number="BME280", lead_time_days=112),
]
CONSTRAINTS = DesignConstraints(60.00, 100.0, 80.0, 25.0, 5.0)

ALTERNATIVES = lookup_alternatives("BME280")

# Verbatim from the run. Both sentences are wrong; only one is wrong in a way
# a grounding check can see.
ERROR_ONE = (
    "For the BME280 sensor, the Bosch BME680 at $3.10 is slightly cheaper "
    "than your current part at $2.40 and ships far sooner."
)
ERROR_TWO = (
    "The ESP32-S3 module at $3.40 has a lead time concern; consider the "
    "SHT31-DIS-B at $1.95 as a second source."
)


def main() -> int:
    truth = ground_truth_for_bom(COMPONENTS, CONSTRAINTS, alternatives=ALTERNATIVES)
    verifier = Verifier()

    rule("Error 1 — the comparison is backwards")
    print(f'  Model wrote: "{ERROR_ONE}"')
    print("  The BME680 is $3.10. The BME280 is $2.40. It is 70 cents MORE")
    print("  expensive. The lookup data's own note even said 'higher cost'.")
    report_one = verifier.verify(ERROR_ONE, truth)
    print(f"\n  Grounding check: {report_one.summary()}")
    print("\n  The check passes, and it is right to. Every number in that")
    print("  sentence is real: $3.10 and $2.40 both appear in the source data.")
    print("  What is false is the word 'cheaper' — a relation between them, not")
    print("  a value. No amount of value-checking can catch that, and a library")
    print("  claiming otherwise would be lying about its own scope.")
    print("\n  Fixed by a different defence: the cost delta is now computed in")
    print("  Python before the prompt is built, and the model is handed the")
    print("  finished comparison to phrase. It is never asked to work out which")
    print("  of two numbers is larger.")

    for alternative in ALTERNATIVES:
        delta = alternative.cost_usd - 2.40
        direction = "MORE expensive" if delta > 0 else "CHEAPER"
        print(f"      pre-computed: {alternative.manufacturer_part_number} is "
              f"${abs(delta):.2f} {direction} than the BME280")

    rule("Error 2 — a fabricated price")
    print(f'  Model wrote: "{ERROR_TWO}"')
    print("  The ESP32-S3 costs $3.20, not $3.40. The model also attached a")
    print("  sensor alternative to a compute module, as if they substituted.")
    report_two = verifier.verify(ERROR_TWO, truth)
    print(f"\n  Grounding check: {report_two.summary()}")
    print("\n  Caught. $3.40 appears nowhere in the source data, so the claim is")
    print("  rejected before it can reach anyone. This is the case the")
    print("  deterministic checker exists for, and it needs no model call to")
    print("  make the call — the value is in the allowed set or it is not.")
    print("\n  The correction fed back to the model names the invented value:")
    print("\n" + "\n".join("    " + line for line in
                           report_two.correction_note().splitlines()))

    rule("What this incident actually argues")
    print("  Two errors, two different failure modes, two different defences.")
    print("  A single layer would have shipped one of them:")
    print()
    print("    fabricated value      -> grounding check      -> caught here")
    print("    wrong relation        -> arithmetic in code   -> never generated")
    print()
    print("  Neither defence is a model checking a model. Both are cheaper than")
    print("  an inference call and neither can itself hallucinate.")

    # Exit non-zero if the library ever stops behaving as documented above.
    ok = report_one.is_grounded and not report_two.is_grounded
    print(f"\n  Reproduction {'confirmed' if ok else 'FAILED — behaviour changed'}.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
