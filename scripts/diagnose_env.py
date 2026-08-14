"""
Diagnostic only — reveals file/path facts, never the actual key value.
Run this from inside AI_CODE/ (or anywhere; it locates itself).
"""
import os

this_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(this_dir, ".env")

print(f"1. Looking for .env at exactly: {env_path}")
print(f"2. Does that exact path exist?  {os.path.exists(env_path)}")

# Common Windows gotcha: Explorer hides known extensions, so a file that
# LOOKS like ".env" might actually be saved as ".env.txt" on disk.
all_files = os.listdir(this_dir)
env_like = [f for f in all_files if "env" in f.lower()]
print(f"3. All filenames in this folder containing 'env': {env_like}")

if os.path.exists(env_path):
    with open(env_path, "rb") as f:
        raw = f.read()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    print(f"4. File starts with a UTF-8 BOM (common Notepad artifact)? {has_bom}")

    text = raw.decode("utf-8-sig")  # utf-8-sig strips a BOM if present
    found_key_line = False
    for line in text.splitlines():
        if line.strip().startswith("ANTHROPIC_API_KEY"):
            found_key_line = True
            key_part = line.split("=", 1)[1].strip() if "=" in line else ""
            print(f"5. Found a line starting with ANTHROPIC_API_KEY. "
                  f"Characters after '=': {len(key_part)} "
                  f"(should be roughly 100+ for a real Anthropic key, 0 means empty)")
            print(f"   Line has surrounding quotes? {key_part.startswith(chr(34)) or key_part.startswith(chr(39))}")
    if not found_key_line:
        print("5. No line starting with 'ANTHROPIC_API_KEY' was found in the file at all.")
else:
    print("4-5. Skipped -- file doesn't exist at the expected path, see line 1-2 above.")

print("\n6. Does python-dotenv itself load it into the environment successfully?")
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path, encoding="utf-8-sig")
    val = os.environ.get("ANTHROPIC_API_KEY")
    print(f"   os.environ has ANTHROPIC_API_KEY set: {val is not None}")
    print(f"   Length of value seen by Python: {len(val) if val else 0}")
except ImportError:
    print("   python-dotenv is not installed -- run: pip install python-dotenv")
