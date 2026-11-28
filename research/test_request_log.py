"""Run: python3 research/test_request_log.py"""
import asyncio, importlib.util, os, pathlib, tempfile, types, json, datetime as dt

os.environ["REQUEST_LOG"] = str(pathlib.Path(tempfile.mkdtemp()) / "log.jsonl")
path = pathlib.Path(__file__).resolve().parent.parent / "infra" / "local" / "request_log.py"
spec = importlib.util.spec_from_file_location("request_log", path); rl = importlib.util.module_from_spec(spec); spec.loader.exec_module(rl)

def ns(**k): return types.SimpleNamespace(**k)
resp = ns(usage=ns(prompt_tokens=1000, completion_tokens=300,
                   prompt_tokens_details=ns(cached_tokens=640), completion_tokens_details=ns(reasoning_tokens=200)),
          choices=[ns(finish_reason="stop")])
t0 = dt.datetime(2026, 11, 26, 12, 0, 0); t1 = t0 + dt.timedelta(seconds=4.5)
judge = {"litellm_call_id": "a", "model": "vertex_ai/gemini-4-neon", "call_type": "acompletion", "stream": True,
         "litellm_params": {"proxy_server_request": {"body": {"model": "gemini-4-neon-judge"}}, "metadata": {}}}
harness = {"litellm_call_id": "b", "model": "x", "litellm_params": {"proxy_server_request": {"body": {"model": "gemini-3.8-flash"}}}}

def lines(): return [json.loads(l) for l in open(os.environ["REQUEST_LOG"])]
rl.instance.log_success_event(judge, resp, t0, t1)
asyncio.run(rl.instance.async_log_success_event(judge, resp, t0, t1))      # same request, second hook: one line only
asyncio.run(rl.instance.async_log_success_event(harness, resp, t0, t1))
rl.instance.log_failure_event({"litellm_call_id": "c", "exception": RuntimeError("boom")}, None, t0, t1)
rl.instance.log_success_event(None, None, None, None)                        # garbage in: must not raise
L = lines()
assert len(L) == 4, len(L)
assert L[0]["is_judge"] and not L[1]["is_judge"] and L[0]["requested_model"] == "gemini-4-neon-judge"
assert (L[0]["prompt_tokens"], L[0]["cached_tokens"], L[0]["reasoning_tokens"], L[0]["latency_s"]) == (1000, 640, 200, 4.5)
assert L[2]["status"] == "failure" and "boom" in L[2]["error"]
print("ok: 4 records, judge flagged, duplicate hook ignored, failure and bad input handled")
