"""Builds the detailed report page for recorded runs: every check, how the agent worked, and the raw files.

  python3 research/run_report.py run-017 run-019 --title "Rung 1 v1" --out page.html \
      --headline run-017="One sentence." --headline run-019="One sentence."

Reads research/run-details/<run>/<task>/ (pulled from the VM), research/runs.jsonl and check_table.py.
Per run: headline, every grader check, how the agent worked (calls, tokens, tools, a call-by-call timeline),
the model's final message, and collapsed raw files (solution.py, grader reports, harness log, task prompt, run record).
Works for rung 0 (one call) and rung 1 (agent loop); a section with no data says so instead of being left out.
"""
import argparse
import html
import json
import pathlib
import re

import markdown

import check_table
import tracker

HERE = pathlib.Path(__file__).resolve().parent
TASK = "data-hall-mep-routing"
CSS = """
:root{--bg:#f6f7f6;--surface:#fff;--fg:#1c2321;--muted:#5d6a66;--line:#dde3e0;--accent:#0f6b5c;--ok:#1b7a43;--okbg:#e2f3e8;--bad:#a8281f;--badbg:#fbe6e3;--warn:#8a5a00;--warnbg:#fff1d6;--infobg:#e8eef0;--code:#f0f3f1}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121715;--surface:#1a211f;--fg:#e4eae7;--muted:#9aa8a3;--line:#2c3733;--accent:#4fc2ac;--ok:#6fd199;--okbg:#17301f;--bad:#ff8f84;--badbg:#3a1c19;--warn:#f0c36a;--warnbg:#33290f;--infobg:#202b2d;--code:#151b19;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#121715;--surface:#1a211f;--fg:#e4eae7;--muted:#9aa8a3;--line:#2c3733;--accent:#4fc2ac;--ok:#6fd199;--okbg:#17301f;--bad:#ff8f84;--badbg:#3a1c19;--warn:#f0c36a;--warnbg:#33290f;--infobg:#202b2d;--code:#151b19;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font:16px/1.55 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:20px 56px}
.wrap{max-width:900px;margin:0 auto;min-width:0}
h1{font-size:1.6rem;line-height:1.2;margin:0 0 10px;text-wrap:balance}
h2{font-size:1.25rem;margin:38px 0 8px;padding-top:14px;border-top:2px solid var(--line);text-wrap:balance}
h3{font-size:1rem;margin:22px 0 6px}
p,li{max-width:74ch}a{color:var(--accent)}
code,pre{font:0.85em ui-monospace,Menlo,Consolas,monospace}
code{background:var(--code);padding:1px 5px;border-radius:4px}
pre{background:var(--code);padding:10px 12px;border-radius:6px;overflow:auto;max-height:520px;white-space:pre-wrap;word-break:break-word}
table{border-collapse:collapse;width:100%;font-size:.86rem;background:var(--surface);border:1px solid var(--line)}
th,td{text-align:left;vertical-align:top;padding:6px 8px;border-bottom:1px solid var(--line)}
th{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.tablewrap{overflow-x:auto;margin:8px 0}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:.78rem;font-weight:600;white-space:nowrap}
.pass{background:var(--okbg);color:var(--ok)}.FAIL{background:var(--badbg);color:var(--bad)}.NOTP{background:var(--warnbg);color:var(--warn)}.info{background:var(--infobg);color:var(--muted)}
.lead{font-size:1.05rem;margin:6px 0 12px}
.kv td:first-child{color:var(--muted);width:46%}
details{margin:8px 0;border:1px solid var(--line);border-radius:6px;background:var(--surface)}
summary{cursor:pointer;padding:8px 12px;font-weight:600}
details>*:not(summary){margin-left:12px;margin-right:12px}
details>pre{margin-bottom:12px}
"""
PILL = {"pass": "pass", "FAIL": "FAIL", "NOT PASSED": "NOTP", "info": "info"}


def esc(s):
    return html.escape(str(s))


def read(path, limit=None):
    p = pathlib.Path(path)
    if not p.is_file():
        return None
    t = p.read_text(encoding="utf-8", errors="replace")
    return t if limit is None or len(t) <= limit else t[:limit] + f"\n... (cut: {len(t) - limit} more characters)"


def table_html(md):
    out = markdown.markdown(md, extensions=["tables"])
    for word, cls in PILL.items():
        out = out.replace(f"<td>{word}</td>", f'<td><span class="pill {cls}">{word}</span></td>')
    return out


def wrap_table(t):
    return f'<div class="tablewrap">{t}</div>'


def details(title, body, open_=False):
    return f"<details{' open' if open_ else ''}><summary>{esc(title)}</summary><pre>{esc(body)}</pre></details>"


def kv(rows):
    return wrap_table("<table class=\"kv\"><tbody>" + "".join(f"<tr><td>{esc(k)}</td><td>{v}</td></tr>" for k, v in rows) + "</tbody></table>")


def parse_log(text):
    """The tagged lines a harness logged, plus tool-call lines in order (each call's tools follow its CALL line)."""
    calls, tools, order = [], {}, []
    summaries = {}
    for line in text.splitlines():
        m = re.search(r": (CALLS|CALL|TOOLS|BUDGET|GUARD|IMAGES) (\{.*|\[.*)\s*$", line)
        if m:
            try:
                data = json.loads(m.group(2))
            except ValueError:
                continue
            if m.group(1) == "CALL":
                calls.append(data)
                order.append(("call", data))
            else:
                summaries[m.group(1)] = data
            continue
        t = re.search(r"pi: (bash|write|edit) (\{.*)", line)
        if t:
            try:
                args = json.loads(t.group(2))
            except ValueError:  # the harness logs only the first 300 characters of a call, so the JSON is cut
                raw = t.group(2)
                args = {"command": raw.split('"command": "', 1)[1].replace("\\n", " ").replace("\\\"", '"') if '"command": "' in raw else raw}
            order.append(("tool", t.group(1), args))
            tools[t.group(1)] = tools.get(t.group(1), 0) + 1
    return calls, summaries, order


def timeline(order):
    """One row per model call with the tool calls that followed it."""
    rows, cur = [], None
    for item in order:
        if item[0] == "call":
            cur = {"call": item[1], "tools": []}
            rows.append(cur)
        elif cur is not None:
            cur["tools"].append(item)
    out = ["| # | prompt | cached | new | out | thinking | stop | what the agent did next |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        c = r["call"]
        p, ca = c.get("prompt_tokens", 0), c.get("cached_reported", 0)
        did = "; ".join(
            f"{t[1]}: " + (t[2].get("command") or t[2].get("path") or "")[:90].replace("\n", " ").replace("|", "/")
            for t in r["tools"]) or "(final answer)"
        out.append(f"| {c.get('n', '')} | {p:,} | {ca:,} | {p - ca:,} | {c.get('completion_tokens', 0):,} | "
                   f"{c.get('reasoning_reported', 0):,} | {c.get('stop_reason') or c.get('finish_reason') or ''} | {did} |")
    return "\n".join(out), rows


def input_rereads(order, log_text):
    names = set()
    m = re.search(r"pi: IMAGES (\{.*)", log_text) or re.search(r"naive: IMAGES (\{.*)", log_text)
    if m:
        try:
            att = json.loads(m.group(1)).get("attached")
            names = {pathlib.PurePosixPath(p).name for p in (att.values() if isinstance(att, dict) else att or [])}
            names |= {n.split("_", 1)[1] for n in names if re.match(r"\d\d_", n)}
        except ValueError:
            pass
    hits = [t for t in order if t[0] == "tool" and t[1] == "bash" and any(n in (t[2].get("command") or "") for n in names)
            and "extract_inputs" not in (t[2].get("command") or "")]
    return len(hits), len(names)


def run_section(run, headline, runs_by_id):
    d = HERE / "run-details" / run["run_id"] / TASK
    metrics = check_table._json(d / "verifier" / "metrics.json")
    label = run.get("label", "")
    model = (run.get("harness") or {}).get("model", "?")
    log_text = "\n".join(read(p) or "" for p in sorted((d / "agent").glob("*.txt")))
    calls, summ, order = parse_log(log_text)
    task = (run.get("tasks") or {}).get(TASK, {})
    secs = task.get("seconds")
    parts = [f'<h2 id="{run["run_id"]}">{esc(run["run_id"])}: {esc(model)}</h2>',
             f'<p class="lead">{esc(headline)}</p>' if headline else "",
             f"<p><code>{esc(label)}</code></p>"]
    inv = run.get("invalid")
    if inv:
        parts.append(f'<p><span class="pill FAIL">INVALID</span> {esc(inv if isinstance(inv, str) else json.dumps(inv))}</p>')
    # how the agent worked
    s = summ.get("CALLS") or {}
    tools = (summ.get("TOOLS") or {})
    if s or calls:
        inp, ca, outp = s.get("input_tokens", 0), s.get("cached_input_tokens", 0), s.get("output_tokens", 0)
        reread, n_inputs = input_rereads(order, log_text)
        rows = [("Model calls (ok / failed)", f"{s.get('ok', len(calls))} / {s.get('failed', 0)}"),
                ("Input tokens, all prompts added up", f"{inp:,}"),
                ("  of which served from the prompt cache", f"{ca:,} ({(100 * ca / inp) if inp else 0:.0f}%)"),
                ("  new, uncached input", f"{inp - ca:,}"),
                ("Largest single prompt", f"{max((c.get('prompt_tokens', 0) for c in calls), default=0):,}"),
                ("Output tokens (includes thinking)", f"{outp:,}"),
                ("  of which thinking", f"{s.get('reasoning_tokens') if s.get('reasoning_tokens') is not None else 'not reported'}"),
                ("Wall time", f"{secs / 60:.1f} min" if secs else "?")]
        if tools:
            rows += [("Tool calls", esc(json.dumps(tools.get("counts", {})))),
                     ("Ran its own deliverable", "yes" if tools.get("ran_deliverable") else "no"),
                     ("Commands that re-opened an input file", f"{reread} (of {n_inputs} input file names)"),
                     ("Input guard refusals", str(tools.get("input_guard_refusals", "not in this version")))]
        if summ.get("BUDGET"):
            b = summ["BUDGET"]
            rows.append(("Call budget", f"{b.get('replies')} of {b.get('max_calls')} used; stopped by budget: {'yes' if b.get('stopped_by_budget') else 'no'}"))
        parts += ["<h3>How the agent worked</h3>", kv(rows)]
        if len(calls) > 1:
            tl, _ = timeline(order)
            parts.append(f"<details><summary>Call by call ({len(calls)} calls): prompt size, cache, output, and what it did next</summary>{wrap_table(table_html(tl))}</details>")
    else:
        parts.append("<p>No call records in this run's logs.</p>")
    # every check
    try:
        parts += ["<h3>Every check</h3>",
                  "<p>A rule marked <span class=\"pill NOTP\">NOT PASSED</span> checked nothing: the submitted model had nothing it applies to. "
                  "The grader lets it through, but a check that tested nothing does not show compliance, so we count it as not passed.</p>",
                  wrap_table(table_html(check_table.table(run["run_id"], TASK)))]
    except Exception as exc:  # a run with no grader files
        parts.append(f"<p>No grader files for this run ({esc(type(exc).__name__)}: {esc(exc)}).</p>")
    # final message and raw files
    final = read(d / "deliverables" / "final_message.md")
    parts += ["<h3>What the model said at the end</h3>", f"<pre>{esc(final)}</pre>" if final else "<p>No final message recorded.</p>"]
    sol = next(iter((d / "deliverables").rglob("solution.py")), None) if (d / "deliverables").is_dir() else None
    raw = [("The script the model wrote (solution.py)", read(sol, 400000) if sol else None),
           ("Grader report: full detail (artifacts.json)", read(d / "verifier" / "artifacts.json", 400000)),
           ("Grader summary (metrics.json)", read(d / "verifier" / "metrics.json", 60000)),
           ("Grader console output (eval.stdout.txt)", read(d / "verifier" / "eval.stdout.txt", 60000)),
           ("Harness log (tagged call, tool and image lines)", "\n".join(l[:600] for l in log_text.splitlines() if re.search(r": (CALLS|CALL|TOOLS|BUDGET|GUARD|IMAGES) |pi: (bash|write|edit) ", l)) or None)]
    try:
        traj = json.loads((d / "agent" / "trajectory.json").read_text(encoding="utf-8"))
        first = next((s_ for s_ in traj["steps"] if s_.get("source") == "user"), None)
        raw.append(("The task prompt the model saw", (first or {}).get("message")))
    except (OSError, ValueError, KeyError):
        raw.append(("The task prompt the model saw", None))
    raw.append(("Run record (runs.jsonl)", json.dumps({k: v for k, v in run.items() if k != "tasks"}, indent=1, default=str)))
    for title, body in raw:
        parts.append(details(title, body) if body else f"<p><em>{esc(title)}: not available.</em></p>")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--title", default="Run report")
    ap.add_argument("--intro", default="")
    ap.add_argument("--extra-md", help="a Markdown file shown after the intro (cross-run findings, next steps)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--headline", action="append", default=[], help="run-id=sentence")
    a = ap.parse_args()
    heads = dict(h.split("=", 1) for h in a.headline)
    runs = {r["run_id"]: r for r in tracker.load_runs()}
    body = [f"<h1>{esc(a.title)}</h1>"]
    if a.intro:
        body.append(f'<p class="lead">{esc(a.intro)}</p>')
    if a.extra_md:
        body.append(markdown.markdown(pathlib.Path(a.extra_md).read_text(encoding="utf-8"), extensions=["tables"]).replace("<table>", '<div class="tablewrap"><table>').replace("</table>", "</table></div>"))
    body.append("<p>" + " · ".join(f'<a href="#{r}">{r}</a>' for r in a.runs) + "</p>")
    body += [run_section(runs[r], heads.get(r, ""), runs) for r in a.runs]
    page = (f"<title>{esc(a.title)}</title>\n<meta name=\"claude:viewport-fit-sides\" content=\"cover\">\n<style>{CSS}</style>\n"
            f"<div class=\"wrap\">\n" + "\n".join(body) + "\n</div>\n")
    pathlib.Path(a.out).write_text(page, encoding="utf-8")
    print(f"wrote {a.out} ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
