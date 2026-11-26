"""Prompt fingerprint for cache estimation. A copy of `fingerprint` in research/kvcache.py:
a harness directory must be self-contained, and research/test_kvcache.py checks the two agree."""
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
