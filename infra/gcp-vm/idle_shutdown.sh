#!/usr/bin/env bash
# VM startup script (create_vm.sh passes it as metadata): installs a timer that powers the VM
# off once it has been idle for IDLE_CHECKS checks in a row (one check every 10 minutes).
# Idle means: nobody logged in over SSH, no task containers, and no run or build process.
# Disable on a running VM:  sudo systemctl disable --now ple-idle.timer
set -euo pipefail
IDLE_CHECKS=3   # 3 x 10 min = 30 minutes idle

cat > /usr/local/bin/ple-idle-check <<EOF
#!/usr/bin/env bash
STATE=/run/ple-idle-count
busy=""
[[ -n "\$(who)" ]] && busy="ssh session"
[[ -z "\$busy" && -n "\$(docker ps -q 2>/dev/null)" ]] && busy="containers running"
[[ -z "\$busy" ]] && pgrep -f 'run_dev.py|eval/run.py|harbor|kit check|docker build|docker compose' >/dev/null && busy="run in progress"
if [[ -n "\$busy" ]]; then echo 0 > \$STATE; echo "busy: \$busy"; exit 0; fi
n=\$(( \$(cat \$STATE 2>/dev/null || echo 0) + 1 )); echo \$n > \$STATE
echo "idle check \$n/$IDLE_CHECKS"
if (( n >= $IDLE_CHECKS )); then echo "idle for 30 min: powering off"; /sbin/shutdown -h now; fi
EOF
chmod +x /usr/local/bin/ple-idle-check

cat > /etc/systemd/system/ple-idle.service <<EOF
[Unit]
Description=Power off the PLE run machine when idle
[Service]
Type=oneshot
ExecStart=/usr/local/bin/ple-idle-check
EOF
cat > /etc/systemd/system/ple-idle.timer <<EOF
[Unit]
Description=Check every 10 minutes whether the PLE run machine is idle
[Timer]
OnBootSec=15min
OnUnitActiveSec=10min
[Install]
WantedBy=timers.target
EOF
rm -f /run/ple-idle-count
systemctl daemon-reload
systemctl enable --now ple-idle.timer
