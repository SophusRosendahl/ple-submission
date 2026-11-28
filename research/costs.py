"""Cost of a run: what it used (tokens, wall-clock) and, where a price is filled in, an estimate.

Per-run numbers come from the tracker. A "model call" is one request to the model endpoint made
by the harness, counted by the harness itself (successful, failed and retried requests apart);
judge calls are not harness calls and are never mixed in. The account's billing is deliberately
not tracked here: the efficiency plots need calls, tokens and runtime, not dollars.
`results.json` gives one `tokens` figure per task, which we treat as input + output together,
so an estimate needs prices for both; `estimate_usd` is an output-tokens-only lower bound.
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent


def prices():
    return json.loads((HERE / "prices.json").read_text(encoding="utf-8"))


def _tokens(t):
    """(input, output) of a task record. results.json stores {'input': n, 'output': n}; older records may hold one number."""
    v = t.get("tokens")
    if isinstance(v, dict):
        return v.get("input") or 0, v.get("output") or 0
    return 0, (v or 0)


def run_usage(run):
    """Totals for one recorded run: tasks with data, calls, input / output tokens, task-hours, longest task."""
    rows = [t for t in run["tasks"].values() if t.get("tokens") is not None or t.get("seconds") is not None]
    inp = sum(_tokens(t)[0] for t in rows)
    out = sum(_tokens(t)[1] for t in rows)
    seconds = [t.get("seconds") or 0 for t in rows]
    summaries = [(t.get("harness") or {}).get("calls") for t in rows]
    calls = [c["ok"] + c["failed"] for c in summaries if c]
    return {"tasks": len(rows), "calls": sum(calls) if calls else None, "input_tokens": inp, "output_tokens": out,
            "task_hours": round(sum(seconds) / 3600, 2), "longest_min": round(max(seconds, default=0) / 60, 1)}


def estimate_usd(run, table=None):
    """Upper-bound model cost in USD, or None when the model has no price yet."""
    price = (table or prices()).get(run["harness"].get("model") or "", {})
    rate = price.get("output")
    if rate is None:
        return None
    return round(run_usage(run)["output_tokens"] / 1e6 * rate, 2)
