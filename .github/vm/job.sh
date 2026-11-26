# Job 3: check the HF token can read the gated dataset; if so, start rung 0 in tmux. VM stays on.
HF=$(sed -n 's/^HF_TOKEN=//p' ~/ple/local.env)
echo "token shape: length ${#HF}, starts '${HF:0:3}'"
echo "whoami: $(curl -s -H "Authorization: Bearer $HF" https://huggingface.co/api/whoami-v2 | jq -r '.name // .error')"
code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $HF" \
  https://huggingface.co/api/datasets/google/physical-engineerings-last-exam/auth-check)
echo "gated dataset access: $code (200 = granted)"
if [[ "$code" == 200 ]]; then
  tmux has-session -t rung0 2>/dev/null && tmux kill-session -t rung0
  tmux new -d -s rung0 "bash ~/ple-submission/infra/gcp-vm/rung0.sh 2>&1 | tee ~/rung0.log"
  sleep 120; echo "--- rung0.log so far:"; tail -20 ~/rung0.log
else
  echo "NOT starting rung 0"
fi
