# Job 2: diagnose the HF token; start rung 0 in tmux only if a gated download works. VM stays on.
HF=$(sed -n 's/^HF_TOKEN=//p' ~/ple/local.env)
echo "token shape: length ${#HF}, starts '${HF:0:3}', has spaces/CR: $([[ "$HF" =~ [[:space:]] ]] && echo yes || echo no)"
echo "whoami: $(curl -s -H "Authorization: Bearer $HF" https://huggingface.co/api/whoami-v2 | jq -r '.name // .error')"
code=$(curl -s -o /dev/null -w '%{http_code}' -L -H "Authorization: Bearer $HF" \
  https://huggingface.co/datasets/google/physical-engineerings-last-exam/resolve/main/README.md)
echo "gated download (with token): $code"
echo "gated download (no token):   $(curl -s -o /dev/null -w '%{http_code}' -L https://huggingface.co/datasets/google/physical-engineerings-last-exam/resolve/main/README.md)"
if [[ "$code" == 200 ]]; then
  tmux new -d -s rung0 "bash ~/ple-submission/infra/gcp-vm/rung0.sh 2>&1 | tee ~/rung0.log"
  sleep 60; echo "--- rung0.log so far:"; tail -20 ~/rung0.log
else
  echo "NOT starting rung 0: token can't download the dataset"
fi
