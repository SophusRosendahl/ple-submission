"""Cost of a run: what it used (tokens, wall-clock) and, where a price is filled in, an estimate.

Per-run numbers come from the tracker. A "model call" is one request to the model endpoint made
by the harness, counted by the harness itself (successful, failed and retried requests apart);
judge calls are not harness calls and are never mixed in. The account's billing is deliberately
not tracked here: the efficiency plots need calls, tokens and runtime, not dollars.
`results.json` gives one `tokens` figure per task, which we treat as input + output together,
so an estimate needs prices for both; with only a single figure it uses the output price as the
upper bound and says so.
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent


def prices():
    return json.loads((HERE / "prices.json").read_text(encoding="utf-8"))


def run_usage(run):
    """Totals for one recorded run: tasks with data, tokens, task-seconds, longest task."""
    rows = [t for t in run["tasks"].values() if t.get("tokens") is not None or t.get("seconds") is not None]
    tokens = sum(t.get("tokens") or 0 for t in rows)
    seconds = [t.get("seconds") or 0 for t in rows]
    calls = [t.get("calls") for t in rows if t.get("calls") is not None]
    return {"tasks": len(rows), "calls": sum(calls) if calls else None, "tokens": tokens, "task_hours": round(sum(seconds) / 3600, 2),
            "longest_min": round(max(seconds, default=0) / 60, 1)}


def estimate_usd(run, table=None):
    """Upper-bound model cost in USD, or None when the model has no price yet."""
    price = (table or prices()).get(run["harness"].get("model") or "", {})
    rate = price.get("output")
    if rate is None:
        return None
    return round(run_usage(run)["tokens"] / 1e6 * rate, 2)
