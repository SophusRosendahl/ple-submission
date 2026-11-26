# stop: yes
# Probe: what output-token limit does each model endpoint accept? (trivial prompt, low effort, a few cents at most)
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
for model in ("gemini-3.8-flash", "gemini-4-neon"):
    for n in (65536, 100000, 131072, 200000, 1000000):
        body = {"model": model, "messages": [{"role": "user", "content": "Reply with the single word OK."}],
                "max_completion_tokens": n, "reasoning_effort": "low"}
        req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read()); print(f"{model:18s} max={n:>8d}  ACCEPTED  usage={d.get('usage', {}).get('completion_tokens')}")
        except urllib.error.HTTPError as e:
            print(f"{model:18s} max={n:>8d}  HTTP {e.code}  {e.read().decode(errors='replace')[:230]!r}")
        except Exception as e:
            print(f"{model:18s} max={n:>8d}  {type(e).__name__}: {e}")
PY
true
