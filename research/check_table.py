"""One table of every check the grader ran on a trial, next to the score.

Reads a trial's grader output from research/run-details/<run_id>/<task>/verifier/ (copied there by
collect_details.py; older runs use research/run-details/<run_id>/verifier/) and lists, per check, whether it
passed and why. Written for `data-hall-mep-routing` (its gates and rule names); another task's grader would
need its own `rows_*` function.

  python3 research/check_table.py run-010 [run-004 ...]
"""
import collections
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent


def verifier_dir(run_id, task="data-hall-mep-routing"):
    for d in (HERE / "run-details" / run_id / task / "verifier", HERE / "run-details" / run_id / "verifier"):
        if d.is_dir():
            return d
    sys.exit(f"no grader files for {run_id} under research/run-details/")


def _json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() and path.stat().st_size else {}


def clash_kinds(clashes):
    """Counts the clashes by what clashed with what, from the element names ('BW-SEG-02 x BW-SEG-07 (bvh:1)')."""
    def kind(name):
        return {"BW": "busway", "CT": "cable tray", "CHW": "chilled water"}.get(name.split("-")[0], "background")
    out = collections.Counter()
    for c in clashes:
        m = re.match(r"(\S+) x (\S+)", c.get("detail", ""))
        if not m:
            out["unparsed"] += 1
            continue
        a, b = kind(m.group(1)), kind(m.group(2))
        if a == b and a != "background":
            out[f"{a} segment x {a} segment (same service)"] += 1
        elif a == "background" and b == "background":
            out["background x background (the model's own rebuild)"] += 1
        elif "background" in (a, b):
            out["service x background"] += 1
        else:
            out[f"{a} x {b} (different services)"] += 1
    return out


def rows(run_id, task="data-hall-mep-routing"):
    d = verifier_dir(run_id, task)
    metrics, report = _json(d / "metrics.json"), _json(d / "artifacts.json").get("report", {})
    status = metrics.get("exec_status") or report.get("exec_status") or "?"
    out = []
    if status.startswith("ERR_") and status not in ("ERR_CLASH",):
        lines = (metrics.get("reason") or "").splitlines()
        err = next((f"{l.strip()} / {lines[i + 1].strip()}" for i, l in enumerate(lines) if "Error" in l and i + 1 < len(lines)), "")
        out.append(("Script ran and wrote the model", "FAIL", f"{status}: {err[:300] or (metrics.get('reason') or '')[:300]}"))
        return out, metrics, report
    out.append(("Script ran and wrote the model", "pass", f"valid={metrics.get('valid')}, {metrics.get('script_seconds')} s"))
    g0 = report.get("gate_0", {})
    out.append(("Gate 0: IFC4 schema / modelling contract", "pass" if g0.get("passed") else "FAIL", f"{g0.get('n_errors', 0)} errors"))
    clashes = report.get("clashes", [])
    g1 = (metrics.get("gates") or {}).get("gate_1_no_hard_clash")
    kinds = "; ".join(f"{n} {k}" for k, n in clash_kinds(clashes).most_common())
    out.append(("Gate 1: no hard clash (> 2 mm)", "pass" if g1 else "FAIL", f"{len(clashes)} clashes of {report.get('checkable_pairs')} checkable pairs: {kinds}" if clashes else "none"))
    g2 = (metrics.get("gates") or {}).get("gate_2_connectivity", {})
    cov = [v for row in (g2.get("coverage") or {}).values() for v in row.values()]
    detail = f"{g2.get('n_rows')} rows, min coverage {min(cov) if cov else '-'} (needs 0.8), {g2.get('n_chw_consumers', 0) - len(g2.get('unreached_consumers') or [])}/{g2.get('n_chw_consumers')} cooling units reached"
    if g2.get("disconnected"):
        detail += "; NOT FED: " + "; ".join(f"{k}: {v}" for k, v in g2["disconnected"].items())[:200]
    out.append(("Gate 2: connectivity / row coverage", "pass" if g2.get("passed") else "FAIL", detail))
    for name, r in (report.get("violations_by_rule") or {}).items():
        sample = (r.get("violations") or [{}])[0].get("detail", "")
        n_chk, n_bad = r.get("n_checkable") or 0, r.get("n_violations") or 0
        if n_chk == 0:   # the rule found nothing in the model to apply to: it passes by default, which proves nothing
            out.append((f"Rule: {name} ({r.get('threshold')})", "n/a",
                        "nothing to check in this model, so it passes by default (not evidence of compliance)"))
            continue
        out.append((f"Rule: {name} ({r.get('threshold')})", "pass" if not n_bad else "FAIL",
                    f"{n_bad} violations in {n_chk} items checked" + (f"; e.g. {sample[:110]}" if sample else "")))
    rl = metrics.get("routed_length") or {}
    if rl.get("l_opt_mm"):
        out.append(("Efficiency: route length vs reference", "info", f"{rl['total_mm'] / 1000:.1f} m against {rl['l_opt_mm'] / 1000:.1f} m (factor {min(1, rl['l_opt_mm'] / rl['total_mm']):.3f})"))
    return out, metrics, report


def table(run_id, task="data-hall-mep-routing"):
    out, metrics, report = rows(run_id, task)
    lines = [f"**{run_id}** · score {metrics.get('combined_score')} · exec_status {metrics.get('exec_status')}", "",
             "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {c} | {s} | {d} |" for c, s, d in out]
    vr, rl = metrics.get("violation_rate"), metrics.get("routed_length") or {}
    if vr is not None and rl.get("l_opt_mm"):
        compliance, eff = 1 - vr, min(1, rl["l_opt_mm"] / rl["total_mm"])
        lines += ["", f"Score formula: compliance {compliance:.3f} (= 1 - {vr:.3f}) x efficiency {eff:.3f} = **{compliance * eff:.3f}** "
                      f"if every gate had passed; the failed gates make it **{metrics.get('combined_score')}**."]
    return "\n".join(lines)


if __name__ == "__main__":
    for rid in sys.argv[1:]:
        print(table(rid)); print()
