"""Environment audit: what can a model see and reach inside the task container? No model calls.

Runs a fixed list of read-only commands in the task container through the same channel an agent's `bash` tool uses
and logs what they print, in chunks tagged `audit[<name>] i/n:`. It lists names, metadata and counts; environment
variables are listed by name only. It writes nothing and ends with `done`.
"""
from __future__ import annotations

import json

import taskbridge

CHUNK = 1500
SEARCH_NAMES = ('-iname "*grader*" -o -iname "*verifier*" -o -iname "*reward*" -o -iname "*answer*" '
                '-o -iname "*expected*" -o -iname "*reference*" -o -iname "tests" -o -iname "*solution*"')
SKIP = '-not -path "/proc/*" -not -path "/sys/*" -not -path "/dev/*" -not -path "/usr/lib/*" -not -path "/usr/share/*"'
CHECKS = [
    ("identity", "id; uname -sr; head -3 /etc/os-release; echo cwd=$(pwd)"),
    ("limits_cgroup", "echo cpu.max: $(cat /sys/fs/cgroup/cpu.max 2>&1); echo memory.max: $(cat /sys/fs/cgroup/memory.max 2>&1); "
                      "echo pids.max: $(cat /sys/fs/cgroup/pids.max 2>&1); nproc; free -m | head -2"),
    ("mounts", "awk '{print $5, $9, $10}' /proc/self/mountinfo | grep -v ' proc \\| sysfs \\| cgroup\\| devpts \\| mqueue ' | head -40"),
    ("disk", "df -h 2>&1 | head -15"),
    ("root_listing", "ls -la / | head -40"),
    ("files_per_top_dir", "for d in /*; do case $d in /proc|/sys|/dev) continue;; esac; echo \"$d $(find $d -xdev 2>/dev/null | wc -l)\"; done"),
    ("names_that_look_like_grading", f"find / -xdev \\( {SEARCH_NAMES} \\) {SKIP} 2>/dev/null | head -40"),
    ("task_folder", "find /app -maxdepth 4 2>/dev/null | head -60; echo; ls -la /app /app/files 2>&1 | head -20"),
    ("writable_dirs", f"find / -xdev -writable -type d {SKIP} 2>/dev/null | head -30"),
    ("env_variable_names", "env | sed 's/=.*//' | sort | tr '\\n' ' '"),
    ("processes", "ps -eo user,pid,args 2>/dev/null | head -20"),
    ("network", "cat /etc/resolv.conf 2>&1 | head -3; python3 -c \"import socket\ntry:\n socket.create_connection(('1.1.1.1',53),3); print('CONNECT 1.1.1.1 OK')\nexcept Exception as e: print('CONNECT 1.1.1.1 failed:', type(e).__name__, e)\""),
    ("python_packages", "pip list 2>/dev/null | wc -l; pip list 2>/dev/null | head -40"),
    ("home_and_root", "ls -la /home /root 2>&1 | head -20"),
]


async def solve(session: taskbridge.Session) -> str:
  """Runs every check, logs its output in chunks, and finishes."""
  for name, command in CHECKS:
    try:
      res = await session.exec(command, timeout_sec=90)
      text = f"exit={res.get('exit_code')}\n{res.get('output') or ''}"
    except Exception as exc:  # an audit must keep going: a failed check is itself a finding
      text = f"check failed: {type(exc).__name__}: {exc}"
    parts = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)] or [""]
    for i, part in enumerate(parts, 1):
      await session.log(f"audit[{name}] {i}/{len(parts)}: " + json.dumps(part))
  return f"Environment audit finished: {len(CHECKS)} read-only checks logged."
