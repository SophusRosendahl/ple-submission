"""LiteLLM callback for our local model proxy: one JSON line per model request, harness and judge alike.

Observes only, never changes a request or response. Loaded next to the competition's own
callbacks (see start_proxy.sh). Path: $REQUEST_LOG, default ~/ple-proxy-requests.jsonl.

Limits, known: LiteLLM reports each request's final outcome. The proxy retries failed upstream
requests itself (`num_retries` in kit/model_proxy/config.yaml), and those hidden retries are not
visible here, so the harness's own count of calls is a lower bound on what the provider served.
A judge request the provider refuses is re-sent once to a fallback model by the competition's
`judge_fallback` callback, which can show up as a second record.
"""
import json
import os
import threading
import time

try:
    from litellm.integrations.custom_logger import CustomLogger
except ImportError:  # lets the file be tested without litellm installed
    CustomLogger = object

PATH = os.environ.get("REQUEST_LOG") or os.path.expanduser("~/ple-proxy-requests.jsonl")
JUDGE_SUFFIX = "-judge"


def _get(obj, *names):
    """First present field among `names` of a dict or object, else None."""
    for name in names:
        v = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
        if v is not None:
            return v
    return None


def _ts(t):
    return t.timestamp() if hasattr(t, "timestamp") else t


def record(kwargs, response_obj, start_time, end_time, status):
    """Builds one log record from LiteLLM's callback arguments, tolerating missing fields."""
    kwargs = kwargs or {}
    params = kwargs.get("litellm_params") or {}
    body = (_get(params, "proxy_server_request") or {}).get("body") or {}
    meta = _get(params, "metadata") or {}
    std = kwargs.get("standard_logging_object") or {}
    resp = kwargs.get("complete_streaming_response") or response_obj
    usage = _get(resp, "usage") if resp is not None else None
    asked = str(_get(body, "model") or "")
    alias = str(_get(meta, "user_api_key_alias") or "")
    prompt_d = _get(usage, "prompt_tokens_details") if usage is not None else None
    compl_d = _get(usage, "completion_tokens_details") if usage is not None else None
    choices = _get(resp, "choices") if resp is not None else None
    finish = _get(choices[0], "finish_reason") if choices else None
    err = kwargs.get("exception") or kwargs.get("traceback_exception") or _get(std, "error_str")
    t0, t1 = _ts(start_time), _ts(end_time)
    return {
        "t_start": t0, "t_end": t1, "latency_s": round(t1 - t0, 3) if t0 is not None and t1 is not None else None,
        "status": status, "call_id": kwargs.get("litellm_call_id"), "call_type": kwargs.get("call_type"),
        "requested_model": asked or None, "model": kwargs.get("model"), "key_alias": alias or None,
        "is_judge": alias.endswith(JUDGE_SUFFIX) or (asked.endswith(JUDGE_SUFFIX) and asked != JUDGE_SUFFIX),
        "stream": bool(kwargs.get("stream")),
        "prompt_tokens": _get(usage, "prompt_tokens") if usage is not None else _get(std, "prompt_tokens"),
        "completion_tokens": _get(usage, "completion_tokens") if usage is not None else _get(std, "completion_tokens"),
        "cached_tokens": _get(prompt_d, "cached_tokens") if prompt_d is not None else None,
        "reasoning_tokens": _get(compl_d, "reasoning_tokens") if compl_d is not None else None,
        "finish_reason": finish, "error": str(err)[:500] if err else None,
    }


class RequestLog(CustomLogger):
    def __init__(self):
        try:
            super().__init__()
        except TypeError:
            pass
        self._lock = threading.Lock()
        self._seen = set()  # LiteLLM may call both the sync and the async hook for one request

    def _write(self, kwargs, response_obj, start_time, end_time, status):
        try:
            rec = record(kwargs, response_obj, start_time, end_time, status)
            key = (rec["call_id"], status)
            with self._lock:
                if rec["call_id"] and key in self._seen:
                    return
                self._seen.add(key)
                if len(self._seen) > 50000:
                    self._seen.clear()
                with open(PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, default=str) + "\n")
        except Exception as exc:  # a logging problem must never break a model request
            print(f"request_log: could not log a request: {type(exc).__name__}: {exc}", flush=True)

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._write(kwargs, response_obj, start_time, end_time, "success")

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._write(kwargs, response_obj, start_time, end_time, "success")

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self._write(kwargs, response_obj, start_time, end_time, "failure")

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self._write(kwargs, response_obj, start_time, end_time, "failure")


instance = RequestLog()
