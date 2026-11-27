"""Build-time patch of the installed Pi: send `thinkingLevel` (not `thinkingBudget`) to Gemini 4 models.

Pi picks Gemini's thinking wire format from the model id (`usesGoogleThinkingLevel`): it knows Gemini 3
Pro/Flash and Gemma 4, not Gemini 4. A Gemini 4 model then gets a token budget, which the API rejects with
HTTP 400 ("Thinking budget is not supported for this model. Use thinking level instead"; run-018). The
rule lives in two installed files; the patch adds `gemini-4` to both and fails loudly if either has changed.

  python3 patch_pi.py <folder that holds node_modules>
"""
import pathlib
import sys

OLD = "/gemma-?4/.test(id)"
NEW = "/gemma-?4/.test(id)||/gemini-4/.test(id)"
FILES = (
    "node_modules/@earendil-works/pi-ai/dist/api/google-shared.js",
    "node_modules/@earendil-works/pi-coding-agent/dist/bundle/chunks/chunk-LTSARG5Q.js",
)

root = pathlib.Path(sys.argv[1])
for rel in FILES:
  path = root / rel
  text = path.read_text(encoding="utf-8")
  if text.count(OLD) != 1:
    sys.exit(f"patch_pi: expected exactly one {OLD!r} in {rel}, found {text.count(OLD)}: Pi changed, check the patch")
  path.write_text(text.replace(OLD, NEW), encoding="utf-8")
  print(f"patch_pi: patched {rel}")
