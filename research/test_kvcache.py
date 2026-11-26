"""Run: python3 research/test_kvcache.py"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import kvcache as k

SYS = {"role": "system", "content": "s" * 6000}
def call(t, msgs, tokens, model="m", rep=None):
    chars, fp = k.fingerprint(msgs)
    return {"t": t, "model": model, "chars": chars, "step": k.STEP, "fp": fp, "prompt_tokens": tokens, "cached_reported": rep}

def test_prefix_is_found():
    a = call(0, [SYS, {"role": "user", "content": "u" * 4000}], 2500)
    b = call(10, [SYS, {"role": "user", "content": "u" * 4000}, {"role": "assistant", "content": "a" * 2000}], 3000)
    e = k.estimate([a, b], min_tokens=0)
    assert e[0]["cached_est"] == 0                      # first call: nothing before it
    assert 0 < e[1]["cached_est"] < 3000                # the shared system+user prefix
    assert e[1]["cached_est"] + e[1]["uncached_est"] == 3000   # the total stays exactly the provider's

def test_ttl_model_and_threshold():
    a = call(0, [SYS], 1500)
    assert k.estimate([a, call(1000, [SYS], 1500)], ttl_s=300, min_tokens=0)[1]["cached_est"] == 0   # expired
    assert k.estimate([a, call(10, [SYS], 1500, model="other")], min_tokens=0)[1]["cached_est"] == 0  # other model
    assert k.estimate([a, call(10, [SYS], 1500)], min_tokens=5000)[1]["cached_est"] == 0              # below minimum
    assert k.estimate([a, call(10, [SYS], 1500)], min_tokens=0)[1]["cached_est"] > 0

def test_different_prefix_is_not_shared():
    a = call(0, [{"role": "system", "content": "x" * 5000}], 1500)
    b = call(5, [{"role": "system", "content": "y" * 5000}], 1500)
    assert k.estimate([a, b], min_tokens=0)[1]["cached_est"] == 0

def test_compare():
    a = call(0, [SYS], 1500, rep=0)
    b = call(5, [SYS], 1500, rep=1400)
    r = k.compare([a, b], min_tokens=0)
    assert r["calls_with_reported"] == 2 and r["cached_reported"] == 1400 and r["cached_est"] > 0

def test_harness_copy_agrees():
    import importlib.util
    path = pathlib.Path(__file__).resolve().parent.parent / "harnesses" / "naive" / "prompt_fingerprint.py"
    spec = importlib.util.spec_from_file_location("pf", path); pf = importlib.util.module_from_spec(spec); spec.loader.exec_module(pf)
    msgs = [SYS, {"role": "user", "content": "\u00e5\u00e4 " * 3000}]
    assert pf.fingerprint(msgs) == k.fingerprint(msgs) and pf.STEP == k.STEP

for name, fn in list(globals().items()):
    if name.startswith("test_"):
        fn(); print("ok", name)
