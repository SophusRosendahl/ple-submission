# stop: yes
# What exactly limits the output? Print Flash's full error; make Neon write a very long answer and see where it stops.
up() { curl -s -o /dev/null -m 5 http://172.17.0.1:4000/health/liveliness; }
if ! up; then
  VERTEXAI_PROJECT=ple-submission bash infra/local/start_proxy.sh >/dev/null 2>&1
  for i in $(seq 40); do up && break; sleep 5; done
fi
up && echo "proxy up" || echo "proxy NOT up"
python3 - <<'PY'
import json, os, urllib.request, urllib.error
env = dict(l.split("=", 1) for l in open(os.path.expanduser("~/ple/local.env")).read().splitlines() if "=" in l)
url, key = env["MODEL_PROXY_URL"].rstrip("/"), env["MODEL_PROXY_KEY"]
def call(body, timeout=900):
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, e.read().decode(errors="replace")
print("=== 1. Flash, max_completion_tokens=100000: the full error")
code, body = call({"model": "gemini-3.8-flash", "messages": [{"role": "user", "content": "OK"}], "max_completion_tokens": 100000, "reasoning_effort": "low"})
print(code, body if isinstance(body, str) else "accepted")
print("=== 2. Neon, max_completion_tokens=200000, asked for a 150,000-word answer, effort low")
code, d = call({"model": "gemini-4-neon", "max_completion_tokens": 200000, "reasoning_effort": "low",
                "messages": [{"role": "user", "content": "Write the word 'alpha' followed by a space, repeated 150000 times. No other text."}]})
if isinstance(d, dict):
    u = d.get("usage", {}); ch = d["choices"][0]
    print("status", code, "| finish_reason:", ch.get("finish_reason"), "| completion_tokens:", u.get("completion_tokens"),
          "| reasoning:", (u.get("completion_tokens_details") or {}).get("reasoning_tokens"), "| text chars:", len(ch["message"].get("content") or ""))
else:
    print(code, d[:600])
PY
true
