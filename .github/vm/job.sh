# stop: idle
# pull: research/network-settings.txt
# Read-only. The environment audit found that a task container on this VM can open an outside connection (CONNECT 1.1.1.1 OK),
# while the evaluation's task container has no network. Where is the network setting made? Only runner and task CONFIGURATION is searched
# (eval/run.py, kit/*.py, Harbor's docker environment code, the task's task.toml and environment/ folder); never the task's tests/ folder.
cd ~/ple-submission && git log -1 --oneline
P=$(ls -d ~/ple /home/*/ple 2>/dev/null | head -1)
H=$(ls -d ~/.local/share/uv/tools/harbor/lib/python3*/site-packages/harbor /home/*/.local/share/uv/tools/harbor/lib/python3*/site-packages/harbor 2>/dev/null | head -1)
T=$(ls -d ~/ple-submission/runs/*/tasks/data-hall-mep-routing 2>/dev/null | tail -1)
{
  echo "== eval/run.py and kit/*.py: lines on network / internet"
  grep -n -i -H "network\|internet\|no-network\|network_mode" "$P"/eval/run.py "$P"/kit/*.py 2>/dev/null | cut -c1-230 | head -40
  echo; echo "== Harbor ($H): lines on allow_internet / network_mode in the docker environment code"
  grep -rn -i -H "allow_internet\|network_mode\|network: none\|no-network" "$H"/environments "$H"/models 2>/dev/null | cut -c1-230 | head -30
  echo; echo "== the task's own configuration ($T): task.toml and environment/ (not tests/)"
  grep -n -i -H "internet\|network\|cpus\|memory" "$T"/task.toml 2>/dev/null | head -20
  ls "$T"/environment 2>/dev/null | head -20
  grep -n -i -H "network\|internet" "$T"/environment/docker-compose* "$T"/environment/Dockerfile 2>/dev/null | cut -c1-200 | head -20
} > research/network-settings.txt 2>&1
cut -c1-200 research/network-settings.txt | head -60
