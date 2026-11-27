# stop: idle
# pull: research/runner-limits.txt
# Read-only. (1) What do the organizers' docs say about the sponsored model endpoints (Vertex AI or Gemini API)?
# (2) Does the runner (kit/ and eval/run.py) already cap each container to 2 CPUs and 4 GB? Only docs and runner settings are searched.
cd ~/ple-submission && git log -1 --oneline
P=$(ls -d ~/ple /home/*/ple 2>/dev/null | head -1)
{
  echo "== docs and README: lines on Vertex / Gemini API / AI Studio / endpoint / proxy"
  grep -n -i -H "vertex\|gemini api\|ai studio\|generativelanguage\|endpoint\|litellm\|sponsored" "$P"/docs/models.md "$P"/docs/local-models.md "$P"/docs/rules.md "$P"/README.md 2>/dev/null | cut -c1-280 | head -60
  echo; echo "== runner (kit/*.py, kit/model_proxy files, eval/run.py): cpu / memory / pids settings"
  grep -n -i -H "cpus\|nano_cpus\|mem_limit\|memory\|pids" "$P"/kit/*.py "$P"/eval/run.py 2>/dev/null | cut -c1-240 | head -40
  echo; echo "== kit/model_proxy: model entries and backends (file names, first lines naming vertex or gemini)"
  ls "$P"/kit/model_proxy 2>/dev/null | head -20
  grep -n -i -H "vertex_ai\|gemini/\|api_base\|litellm_params" "$P"/kit/model_proxy/*.yaml "$P"/kit/model_proxy/*.yml 2>/dev/null | cut -c1-200 | head -20
} > research/runner-limits.txt 2>&1
cut -c1-200 research/runner-limits.txt | head -60
