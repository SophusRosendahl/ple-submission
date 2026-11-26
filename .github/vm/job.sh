# sync: no
# Read only: how the model proxy is configured (can it log every request, harness and judge alike?).
cd ~/ple/kit/model_proxy 2>/dev/null && ls -la && echo "--- start.sh:" && cat start.sh | head -60
echo "--- config files:"; for f in *.yaml *.yml *.py; do [ -f "$f" ] && { echo "=== $f"; head -80 "$f"; }; done
echo "--- proxy log tail:"; tail -5 ~/ple-proxy.log | cut -c1-300
