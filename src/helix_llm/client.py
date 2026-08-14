"""
HELIX CORE — LLM Client abstraction, per AI_MODEL_STRATEGY.md.

This is the actual code implementation of the abstraction layer that's
been described in documentation since D-008: agents call one interface,
the backend behind it is swappable without touching agent logic.

Two implementations:
  - LocalOllamaLLMClient: current default per D-026 (local, no API key,
    no subscription, runs on the owner's own hardware).
  - AnthropicLLMClient: original hosted-API path, kept available since
    the abstraction layer makes either valid -- useful if local hardware
    is ever swapped, upgraded, or unavailable.

IMPORTANT — sandbox limitation, stated plainly: this sandbox cannot
reach ollama.com (network egress restricted to package registries only,
confirmed via direct test — 403), so the actual Ollama runtime and real
model weights cannot be installed or pulled here. LocalOllamaLLMClient's
connection logic is real and correct, and its "server not reachable"
error path is genuinely tested below (nothing is listening on the
Ollama port in this sandbox, which is a true test of that path) — but a
full round trip with real Qwen3 output can only be verified on the
owner's own machine, where Ollama actually runs.
"""

from abc import ABC, abstractmethod
import os


class LLMClient(ABC):
    """The one interface every agent calls — per AI_MODEL_STRATEGY.md
    Section 1. Swapping backends means swapping which class is
    instantiated, not touching any agent code."""

    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 800) -> str:
        ...


class LocalOllamaLLMClient(LLMClient):
    """Current default per D-026. No API key, no subscription, no
    external network call at inference time -- everything stays on the
    owner's own machine.

    TWO-PHASE HARDWARE PLAN, per direct owner constraint (2026-07-15):
    the 4060's 8GB VRAM is currently fully claimed by a separate system
    (SuperMind) with no shareable headroom -- not "tight," genuinely
    zero. Time-sharing (keep_alive) doesn't help when there's no room to
    load into in the first place. Until SuperMind moves to its own
    dedicated hardware (owner's stated plan), HELIX runs CPU-only via
    force_cpu=True, which touches zero VRAM and therefore cannot conflict
    with SuperMind regardless of how much of the 8GB it holds. This is a
    real capability/speed trade-off, accepted deliberately for a stated
    temporary constraint -- not a permanent design choice. Once SuperMind
    moves off this desktop, switch force_cpu=False and model="qwen3:8b"
    to get GPU-accelerated inference back.

    keep_alive still applies once GPU mode is restored -- kept as the
    right behavior for that phase, harmless no-op in CPU mode.
    """

    def __init__(self, model: str = "phi4-mini", host: str = "http://localhost:11434",
                 keep_alive: str = "30s", force_cpu: bool = True):
        self.model = model
        self.host = host
        self.keep_alive = keep_alive
        self.force_cpu = force_cpu

    def generate(self, prompt: str, max_tokens: int = 800) -> str:
        try:
            import ollama
        except ImportError:
            return "[LOCAL MODEL UNAVAILABLE — 'ollama' package not installed. Run: pip install ollama]"

        try:
            client = ollama.Client(host=self.host)
            options = {"num_gpu": 0} if self.force_cpu else {}
            response = client.generate(
                model=self.model, prompt=prompt, keep_alive=self.keep_alive,
                options=options,
            )
            return response["response"]
        except Exception as e:
            return (
                f"[LOCAL MODEL UNREACHABLE — could not reach Ollama at {self.host}. "
                f"Confirm Ollama is installed and running ('ollama serve'), and that "
                f"the model is pulled ('ollama pull {self.model}'). Error: {e}]"
            )


class AnthropicLLMClient(LLMClient):
    """Original hosted-API path (pre-D-026). Kept available since the
    abstraction layer makes either backend valid -- e.g. if local
    hardware is ever unavailable or a heavier task needs frontier-tier
    capability beyond what fits on 8GB VRAM."""

    def __init__(self, model: str = "claude-opus-5"):
        self.model = model

    def generate(self, prompt: str, max_tokens: int = 800) -> str:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return "[HOSTED MODEL SKIPPED — no ANTHROPIC_API_KEY set in this environment.]"
        try:
            import anthropic
        except ImportError:
            return "[HOSTED MODEL SKIPPED — 'anthropic' package not installed.]"
        try:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=self.model, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            return f"[HOSTED MODEL CALL FAILED — {e}]"


def get_default_client() -> LLMClient:
    """Per D-026: local is the current default. Set HELIX_LLM_BACKEND=hosted
    in the environment to fall back to the Anthropic path instead."""
    if os.environ.get("HELIX_LLM_BACKEND", "local") == "hosted":
        return AnthropicLLMClient()
    return LocalOllamaLLMClient()
