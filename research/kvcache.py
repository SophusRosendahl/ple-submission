"""Our own estimate of which input tokens were served from the provider's prompt (KV) cache.

Why: providers report cached tokens inconsistently or not at all, and the evaluator's token figure
does not say how it treats them. So each harness logs, per model call, a compact fingerprint of
its prompt (hashes of the prompt prefix every `step` characters, never the text itself), and this
module replays those calls through a simulated prefix cache.

The model of a prefix cache (an assumption, checked against reported figures by `compare`):
  * a call can reuse the longest prefix it shares with an earlier call of the same model that was
    made at most `ttl_s` seconds before (calls from other tasks count: the system prompt is shared);
  * only a prefix worth at least `min_tokens` tokens is cached;
  * tokens are estimated from characters: cached = prompt_tokens * shared_chars / total_chars,
    so the provider's own prompt_tokens total is kept exact and only the split is estimated;
  * the shared prefix is measured to a resolution of `step` characters, rounded down.
`ttl_s` and `min_tokens` differ by provider and are NOT known here: the defaults are placeholders
to be calibrated with `compare` against calls that report `cached_reported`.

A call record (what the harness logs as `CALL {...}`):
  {"t": epoch seconds, "model": str, "chars": int, "step": int, "fp": [hex, ...],
   "prompt_tokens": int, "cached_reported": int | None}
"""
import hashlib
import json

STEP = 1000


def fingerprint(messages, step=STEP):
    """(total chars, prefix hashes) of a chat prompt. Prefix-preserving: a prompt that extends
    another one starts with the same hashes. Cost is linear in the prompt length."""
    text = "".join(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n" for m in messages)
    h, fp = hashlib.sha1(), []
    for i in range(0, len(text) - step + 1, step):
        h.update(text[i:i + step].encode("utf-8"))
        fp.append(h.copy().hexdigest()[:10])
    return len(text), fp


def shared_chars(fp_a, fp_b, step=STEP):
    """Characters of common prefix, to a resolution of `step`, rounded down."""
    n = 0
    for a, b in zip(fp_a, fp_b):
        if a != b:
            break
        n += 1
    return n * step


def estimate(calls, ttl_s=300, min_tokens=1024):
    """Adds `cached_est` and `uncached_est` input tokens to each call, in time order."""
    out, seen = [], []
    for c in sorted(calls, key=lambda c: c["t"]):
        best = 0
        for p in seen:
            if p["model"] == c["model"] and 0 <= c["t"] - p["t"] <= ttl_s:
                best = max(best, shared_chars(c["fp"], p["fp"], c["step"]))
        cached = int(c["prompt_tokens"] * min(best, c["chars"]) / c["chars"]) if c["chars"] else 0
        if cached < min_tokens:
            cached = 0
        out.append({**c, "cached_est": cached, "uncached_est": c["prompt_tokens"] - cached})
        seen.append(c)
    return out


def compare(calls, **params):
    """Estimated against reported cached tokens, over the calls that report them."""
    est = estimate(calls, **params)
    rep = [c for c in est if c.get("cached_reported") is not None]
    return {
        "calls": len(est), "calls_with_reported": len(rep),
        "input_tokens": sum(c["prompt_tokens"] for c in est),
        "cached_est": sum(c["cached_est"] for c in est),
        "cached_est_on_reported_calls": sum(c["cached_est"] for c in rep),
        "cached_reported": sum(c["cached_reported"] for c in rep),
        "mean_abs_error_tokens": (sum(abs(c["cached_est"] - c["cached_reported"]) for c in rep) / len(rep)) if rep else None,
    }
