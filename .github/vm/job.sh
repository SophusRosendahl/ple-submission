# Job 1: check the HF token, start the model proxy, check the models answer. VM stays on.
set -e
git -C ~/ple pull -q --ff-only || echo "ple pull failed"
HF=$(sed -n 's/^HF_TOKEN=//p' ~/ple/local.env)
echo "HF user: $(curl -s -H "Authorization: Bearer $HF" https://huggingface.co/api/whoami-v2 | jq -r '.name // .error')"
echo "HF dataset access: $(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $HF" https://huggingface.co/api/datasets/google/physical-engineerings-last-exam)"
VERTEXAI_PROJECT=ple-submission bash infra/local/start_proxy.sh
sleep 90
tail -15 ~/ple-proxy.log
python3 infra/local/check_models.py
