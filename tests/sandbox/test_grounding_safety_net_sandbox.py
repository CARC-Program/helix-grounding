"""
Two things tested here:
1. check_full_grounding() against the EXACT fabricated text pasted back
   from the user's real field-test session (verbatim, not paraphrased) --
   confirms the safety net actually catches the specific inventions that
   already happened, not just hypothetical ones.
2. synthesize_recommendations_validated()'s reject/regenerate flow, using
   a mock LLM client so the retry logic itself can be verified without
   needing a real Ollama call in this sandbox.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from helix_bom.agent import BOMReviewAgent, Component, DesignConstraints
import helix_llm.client as llm_client
from test_variated_1_over_budget_only_sandbox import build_bom as build_test1_bom
from test_variated_3_physical_fit_only_sandbox import build_bom as build_test3_bom


# Exact text pasted back from the real session, verbatim
TEST1_REAL_FABRICATED_TEXT = (
    "After reviewing your build against its budget constraints of $30.00 with an "
    "identified overspend by 18.45 dollars due primarily from the High-end MCU "
    "module costing a total of $36.00, I recommend addressing this critical issue "
    "first.\n\n1. **High-End MCU Module ($36)**: Investigate alternative MCUs...\n"
    "2. The **Premium Display module** ($22) and other components should be "
    "reviewed next..."
)

TEST3_REAL_FABRICATED_TEXT = (
    "an oversized display panel. Currently listed as 85x50x4mm and costing $5 "
    "each ($35 total for your build)—this exceeds both width and depth...\n"
    "a compact MCU unit... at 12x12x1.5mm and costs $3 each ($36 total for the "
    "compute category)."
)


def run_detection_tests():
    print("=== Part 1: detection against the real fabricated text from this session ===\n")

    agent = BOMReviewAgent()

    components1, constraints1 = build_test1_bom()
    issues1 = agent.check_full_grounding(TEST1_REAL_FABRICATED_TEXT, components1, constraints1)
    print("Test 1 real text — issues found:", issues1)
    assert "dollar_amounts" in issues1, "Expected the fabricated $36 to be caught"
    assert 36.0 in issues1["dollar_amounts"], f"Expected 36.0 specifically, got {issues1['dollar_amounts']}"
    print("[PASS] Test 1's fabricated $36.00 correctly caught\n")

    components3, constraints3 = build_test3_bom()
    issues3 = agent.check_full_grounding(TEST3_REAL_FABRICATED_TEXT, components3, constraints3)
    print("Test 3 real text — issues found:", issues3)
    assert "dollar_amounts" in issues3
    assert 36.0 in issues3["dollar_amounts"] and 35.0 in issues3["dollar_amounts"], (
        f"Expected both 36.0 and 35.0 caught, got {issues3['dollar_amounts']}"
    )
    print("[PASS] Test 3's fabricated $36 AND $35 both correctly caught\n")

    # Sanity check: a genuinely clean, correct text must NOT be flagged
    clean_text = (
        "Your BOM totals $48.45 against a $30.00 budget, an overage of $18.45. "
        "The High-end MCU module is $18.00 and the Premium Display module is $22.00."
    )
    issues_clean = agent.check_full_grounding(clean_text, components1, constraints1)
    print("Clean, correct text — issues found:", issues_clean)
    assert issues_clean == {}, f"Expected no issues on genuinely correct text, got {issues_clean}"
    print("[PASS] Genuinely correct text produces zero false positives\n")


class _MockBadThenGoodClient:
    """Simulates an LLM that fabricates on its first attempt, then
    produces clean text on retry -- lets the reject/regenerate loop be
    tested without a real Ollama call."""
    def __init__(self):
        self.call_count = 0

    def generate(self, prompt, max_tokens=800):
        self.call_count += 1
        if self.call_count == 1:
            return "Your MCU costs a total of $36.00, which is concerning."  # fabricated
        return "Your MCU costs $18.00 and your BOM totals $48.45 against a $30.00 budget."  # correct


def run_retry_flow_test():
    print("=== Part 2: reject/regenerate flow with a mock client ===\n")

    agent = BOMReviewAgent()
    components, constraints = build_test1_bom()
    result = agent.review(components, constraints)

    mock_client = _MockBadThenGoodClient()
    original_get_default_client = llm_client.get_default_client
    llm_client.get_default_client = lambda: mock_client

    try:
        outcome = agent.synthesize_recommendations_validated(result, components, constraints, max_retries=2)
    finally:
        llm_client.get_default_client = original_get_default_client

    print(f"Mock client was called {mock_client.call_count} times")
    print(f"Final validated: {outcome['validated']}")
    print(f"Rejected attempts logged: {len(outcome['rejected_attempts'])}")
    for r in outcome["rejected_attempts"]:
        print(f"  Attempt {r['attempt']} rejected — invented: {r['issues']}")
    print(f"Final delivered text: {outcome['text']}")

    assert mock_client.call_count == 2, "Expected exactly 2 calls: 1 rejected, 1 accepted"
    assert outcome["validated"] is True
    assert len(outcome["rejected_attempts"]) == 1
    assert outcome["rejected_attempts"][0]["issues"].get("dollar_amounts") == [36.0]
    print("\n[PASS] First fabricated attempt correctly rejected and logged, "
          "second clean attempt correctly accepted and delivered\n")


def run_exhausted_retries_test():
    print("=== Part 3: all retries exhausted -- must fall back safely, never deliver bad text ===\n")

    class _AlwaysBadClient:
        def generate(self, prompt, max_tokens=800):
            return "Your MCU costs a total of $999.00, which is concerning."

    agent = BOMReviewAgent()
    components, constraints = build_test1_bom()
    result = agent.review(components, constraints)

    original_get_default_client = llm_client.get_default_client
    llm_client.get_default_client = lambda: _AlwaysBadClient()
    try:
        outcome = agent.synthesize_recommendations_validated(result, components, constraints, max_retries=2)
    finally:
        llm_client.get_default_client = original_get_default_client

    print(f"Validated: {outcome['validated']}")
    print(f"Rejected attempts: {len(outcome['rejected_attempts'])}")
    print(f"Final text delivered: {outcome['text']}")

    assert outcome["validated"] is False, "Must never claim success when all retries stayed ungrounded"
    assert len(outcome["rejected_attempts"]) == 3, "Expected 3 total attempts (1 + 2 retries)"
    assert "AUTOMATED SYNTHESIS FAILED GROUNDING VALIDATION" in outcome["text"]
    assert "999" not in outcome["text"], "Fabricated content must never reach the final delivered text"
    print("\n[PASS] Exhausted retries correctly fall back to a safe message, "
          "fabricated content never delivered\n")


if __name__ == "__main__":
    run_detection_tests()
    run_retry_flow_test()
    run_exhausted_retries_test()
    print("[SANDBOX TEST PASSED] Grounding safety net verified: detection, retry-with-correction, and safe fallback all confirmed.")
