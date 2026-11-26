"""Cost of a run: what it used (tokens, wall-clock) and, where a price is filled in, an estimate.

Per-run numbers come from the tracker. The account's actual spend (VM, disk, Vertex AI) comes
from the Cloud Billing export, saved as research/billing_by_day.csv by a runner job.
`results.json` gives one `tokens` figure per task, which we treat as input + output together,
so an estimate needs prices for both; with only a single figure it uses the output price as the
upper bound and says so.
"""
import csv
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
    return {"tasks": len(rows), "tokens": tokens, "task_hours": round(sum(seconds) / 3600, 2),
            "longest_min": round(max(seconds, default=0) / 60, 1)}


def estimate_usd(run, table=None):
    """Upper-bound model cost in USD, or None when the model has no price yet."""
    price = (table or prices()).get(run["harness"].get("model") or "", {})
    rate = price.get("output")
    if rate is None:
        return None
    return round(run_usage(run)["tokens"] / 1e6 * rate, 2)


def billing_by_day():
    """Rows of research/billing_by_day.csv (day, service, cost), or [] if not pulled yet."""
    path = HERE / "billing_by_day.csv"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))
