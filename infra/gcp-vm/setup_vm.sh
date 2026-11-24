#!/usr/bin/env bash
# One-time setup on the run machine: Docker, uv, Harbor, and the competition repository.
# Run on the VM as your normal user:  bash setup_vm.sh
set -euo pipefail

if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi
if ! command -v uv >/dev/null && [[ ! -x "$HOME/.local/bin/uv" ]]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv tool install harbor==0.20.0 --with websockets
sudo apt-get update -qq && sudo apt-get install -y -qq git tmux jq

cd "$HOME"
[[ -d ple ]] || git clone https://github.com/SophusRosendahl/ple.git
echo
echo "Next:"
echo "  1. log out and back in (so Docker works without sudo)"
echo "  2. clone ple-submission (private): gh auth login, or git clone with a token"
echo "  3. bash ple-submission/infra/local/start_proxy.sh"
