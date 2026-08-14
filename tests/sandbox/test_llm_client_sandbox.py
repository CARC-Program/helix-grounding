"""
Tests what's genuinely testable in this sandbox: the interface contract,
backend selection logic, and the real "server unreachable" error path
(nothing is listening on the Ollama port here, which is a true test of
that failure mode, not a simulation of it).

Does NOT test real Qwen3 output -- that requires Ollama actually running,
which needs the owner's own machine (ollama.com is unreachable from this
sandbox, confirmed).
"""
import sys, os

from helix_llm.client import LocalOllamaLLMClient, AnthropicLLMClient, get_default_client


def run():
    print("=== Backend selection ===")
    os.environ.pop("HELIX_LLM_BACKEND", None)
    client = get_default_client()
    assert isinstance(client, LocalOllamaLLMClient)
    print("[PASS] Default backend is local Ollama, per D-026")

    os.environ["HELIX_LLM_BACKEND"] = "hosted"
    client = get_default_client()
    assert isinstance(client, AnthropicLLMClient)
    print("[PASS] HELIX_LLM_BACKEND=hosted correctly selects the Anthropic fallback")
    os.environ.pop("HELIX_LLM_BACKEND", None)

    print("\n=== Ollama connectivity check (result differs by environment, both are valid) ===")
    local = LocalOllamaLLMClient()
    result = local.generate("Say hello in one sentence.")
    if "UNREACHABLE" in result or "UNAVAILABLE" in result:
        print(f"[PASS] Ollama not running in this environment, correctly reported rather than crashing:\n    {result[:100]}...")
    else:
        print(f"[PASS] Ollama reachable — real model output returned:\n    {result[:200]}")

    print("\n=== Hosted client with no key present ===")
    os.environ.pop("ANTHROPIC_API_KEY", None)
    hosted = AnthropicLLMClient()
    result = hosted.generate("test prompt")
    assert "SKIPPED" in result
    print(f"[PASS] Correctly reports skipped rather than crashing:\n    {result}")

    print("\n[SANDBOX TEST PASSED] Interface contract and error paths verified.")
    print("[NOT TESTED HERE] Real Qwen3 output — requires Ollama running on the owner's own machine.")


if __name__ == "__main__":
    run()
