#!/usr/bin/env bash
# Detached knowledge-point run (resumable: finished chapters are skipped). Idle suspend inhibited while it runs.
#   start:  setsid nohup scripts/run_kps.sh >/dev/null 2>&1 &
cd "$(dirname "$0")/.."
mkdir -p output/knowledge
INHIBIT=()
command -v kde-inhibit >/dev/null && [ -n "$DBUS_SESSION_BUS_ADDRESS" ] && INHIBIT=(kde-inhibit --power)
"${INHIBIT[@]}" python3 scripts/build_kps.py run >> output/knowledge/run.log 2>&1
echo "$(date -u +%FT%T) knowledge-point chapters done" >> output/knowledge/run.log
