# OLLAMA SETUP AND SANDBOX TESTING GUIDE

**Last updated:** 2026-07-15
**Target hardware:** RTX 4060, 8GB VRAM — currently fully claimed by
SuperMind with no shareable headroom (owner-confirmed, 2026-07-15).
**Current phase model:** `phi4-mini` (3.8B), forced to CPU-only —
touches zero VRAM, cannot conflict with SuperMind regardless of how much
of the 8GB it holds. Slower than GPU inference; correct trade for a
stated temporary constraint.
**Later phase (once SuperMind moves to its own hardware):** switch to
`qwen3:8b`, GPU-accelerated — both tags confirmed directly against
Ollama's own library.

---

## 1. DOWNLOAD AND INSTALL

1. Go to https://ollama.com/download and download the Windows installer.
2. Run it. The installer sets up Ollama as a background service that
   starts automatically (you'll see a small icon in the system tray) —
   you do **not** need to manually run a server command on Windows in
   normal use.

## 2. VERIFY IT'S ACTUALLY RUNNING

Open a new terminal (Command Prompt or PowerShell) and run:

```
ollama --version
```

Should print a version number. If it errors as "not recognized," close
and reopen your terminal (PATH updates need a fresh terminal window) or
restart your machine once.

Then confirm the server itself is reachable:

```
curl http://localhost:11434
```

Should return `Ollama is running`. If it doesn't, look for the Ollama
icon in your system tray — right-click it and confirm it's not paused,
or start it from the Start Menu.

**Note:** requires Ollama 0.5.13 or later for phi4-mini. `ollama --version`
from step above will confirm this; update via the installer again if needed.

## 3. PULL THE MODEL — CURRENT PHASE (CPU-only, coexists with SuperMind)

```
ollama pull phi4-mini
```

This downloads a few GB — much smaller and faster than qwen3:8b. Only
needs to happen once.

## 4. QUICK MANUAL SANITY CHECK (before touching HELIX code at all)

```
ollama run phi4-mini "Say hello in one sentence."
```

If you get a real sentence back, Ollama and the model are both working
correctly and the rest is just HELIX code talking to something that
already works. This should not touch your VRAM at all in this phase —
HELIX's code forces CPU execution specifically so it can't compete with
SuperMind for GPU memory.

## 5. INSTALL HELIX'S PYTHON DEPENDENCIES (if not already done)

From `10_SOFTWARE_DEVELOPMENT\AI_CODE\`:

```
python3 -m pip install -r ..\SERVER_APPLICATIONS\requirements.txt
```

## 6. RUN THE SANDBOX TESTS — DIRECT FILE LOCATIONS

Exact paths, assuming your project sits at
`C:\Users\User\Downloads\Project Helix\` (adjust only if yours differs):

**Test 1 — LLM client, now with a real Ollama server behind it:**
```
cd "C:\Users\User\Downloads\Project Helix\10_SOFTWARE_DEVELOPMENT\TESTING"
python3 test_llm_client_sandbox.py
```
Expect the "UNREACHABLE" result from before to disappear — it should now
report a real connection instead.

**Test 2 — full BOM review agent, deterministic checks + real synthesis:**
```
cd "C:\Users\User\Downloads\Project Helix\10_SOFTWARE_DEVELOPMENT\TESTING"
python3 test_bom_review_sandbox.py
```
The "LLM synthesis layer" section at the bottom should now show a real,
written paragraph of recommendations instead of any skip/unreachable
message — this is the first time you'll see actual model output from
this project. It will be slower than a GPU response and somewhat less
sophisticated than qwen3:8b would produce — both expected, both the
correct trade for the current hardware constraint.

**Test 3 — orchestrator, the full request-to-response pipeline:**
```
cd "C:\Users\User\Downloads\Project Helix\10_SOFTWARE_DEVELOPMENT\TESTING"
python3 test_orchestrator_sandbox.py
```

## 7. LATER PHASE — ONCE SUPERMIND MOVES OFF THIS DESKTOP

Two changes, both already supported by the existing code:
```
ollama pull qwen3:8b
```
Then in llm_client.py, change the LocalOllamaLLMClient defaults:
`model="qwen3:8b"`, `force_cpu=False` — GPU-accelerated inference,
faster and more capable, safe once the 4060's full 8GB is genuinely free.

## 8. WHAT TO SEND BACK

Just paste whatever the terminal prints — pass or fail, full output, not
a summary. If something's wrong, the actual error text is what lets this
get fixed quickly instead of guessed at.
