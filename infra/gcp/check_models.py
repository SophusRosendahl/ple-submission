"""Checks the model proxy: one text call and one image call per model.

Settles two questions before any real run: does each model answer through the proxy, and does
it accept image input (the drawing-based tasks depend on it). Uses low reasoning effort to keep
the check cheap. Standard library only.

  python3 check_models.py                      # claude-opus-5-5 and gemini-4-neon
  python3 check_models.py gemini-4-carbon ...  # other models
"""
import base64
import json
import os
import pathlib
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib

ENV_FILE = pathlib.Path(os.environ.get("PLE_ENV", pathlib.Path.home() / "ple" / "local.env"))
DEFAULT_MODELS = ["claude-opus-5-5", "gemini-4-neon"]


def env():
    values = dict(line.split("=", 1) for line in ENV_FILE.read_text().splitlines() if "=" in line)
    return values["MODEL_PROXY_URL"].rstrip("/"), values["MODEL_PROXY_KEY"]


def png_square(rgb, size=64):
    """A solid-colour PNG, built without any imaging library."""
    row = b"\x00" + bytes(rgb) * size
    raw = row * size

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def call(url, key, model, content):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 2000,
        "reasoning_effort": "low",
    }
    req = urllib.request.Request(f"{url}/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:300]}", time.time() - start
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}", time.time() - start
    text = (data["choices"][0]["message"].get("content") or "").strip()
    return True, text, time.time() - start


def main():
    url, key = env()
    models = sys.argv[1:] or DEFAULT_MODELS
    image = "data:image/png;base64," + base64.b64encode(png_square((220, 30, 30))).decode()
    failed = False
    for model in models:
        ok, text, secs = call(url, key, model, "Reply with the single word OK.")
        print(f"{model:24s} text   {'PASS' if ok and 'ok' in text.lower() else 'FAIL'}  {secs:5.1f}s  {text[:80]!r}")
        failed |= not ok
        ok, text, secs = call(url, key, model, [
            {"type": "text", "text": "What colour is this square? Answer with one word."},
            {"type": "image_url", "image_url": {"url": image}},
        ])
        seen = ok and "red" in text.lower()
        print(f"{model:24s} image  {'PASS' if seen else 'FAIL'}  {secs:5.1f}s  {text[:80]!r}")
        failed |= not seen
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
