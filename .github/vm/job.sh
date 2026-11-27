# stop: yes
# Round 2: the other five sheets (task INPUTS, never the grader's tests/): where is the IFC class / property-set contract?
up() { curl -s -o /dev/null -m 5 http://172.17.0.1:4000/health/liveliness; }
if ! up; then
  VERTEXAI_PROJECT=ple-submission bash infra/local/start_proxy.sh >/dev/null 2>&1
  for i in $(seq 40); do up && break; sleep 5; done
fi
python3 - <<'PY'
import base64, glob, json, os, urllib.request, urllib.error
env = dict(l.split("=", 1) for l in open(os.path.expanduser("~/ple/local.env")).read().splitlines() if "=" in l)
url, key = env["MODEL_PROXY_URL"].rstrip("/"), env["MODEL_PROXY_KEY"]
root = os.path.expanduser("~/.cache/plebench/tasks")
def sheet(name):
    hits = [p for p in glob.glob(f"{root}/**/{name}", recursive=True) if "data-hall-mep-routing" in p and "/tests/" not in p and "evaluator" not in p]
    return hits[0] if hits else None
QUESTION = ("This is a sheet from a data-hall drawing set. Transcribe VERBATIM and completely every note, legend, table or callout on it "
            "that concerns any of: (1) an IFC class, ObjectType, PredefinedType, property-set name or property name/value required or named for ANY element "
            "(racks, CRAH, PDU, columns, sprinkler heads, containment roof or door, access floor or floor tiles, cable tray, busway, pipe); "
            "(2) the access floor or floor tiles (size, thickness, whether tiles are separate elements); "
            "(3) sprinkler heads under the containment roof or any wide obstruction (the head line); "
            "(4) any modelling contract, naming or tagging rule. Quote exactly, keep numbers and units, and write 'none on this sheet' for an item with nothing. No commentary.")
for name in ("A-601.png", "F-101.png", "A-301.png", "M-101.png", "E-101.png"):
    p = sheet(name)
    print(f"\n=================== {name}: {p}")
    if not p: continue
    b64 = base64.b64encode(open(p, "rb").read()).decode()
    body = {"model": "gemini-4-neon", "reasoning_effort": "low", "max_completion_tokens": 30000,
            "messages": [{"role": "user", "content": [{"type": "text", "text": QUESTION},
                                                       {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]}]}
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            d = json.loads(r.read()); print(d["choices"][0]["message"].get("content") or "(empty)")
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode(errors="replace")[:400])
PY
true
