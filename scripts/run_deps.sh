#!/usr/bin/env bash
# Detached derivation-source run (resumable: finished knowledge points are skipped). Idle suspend inhibited meanwhile.
#   start:  setsid nohup scripts/run_deps.sh >/dev/null 2>&1 &
cd "$(dirname "$0")/.."
mkdir -p output/knowledge/deps
INHIBIT=()
command -v kde-inhibit >/dev/null && [ -n "$DBUS_SESSION_BUS_ADDRESS" ] && INHIBIT=(kde-inhibit --power)
"${INHIBIT[@]}" python3 scripts/build_deps.py run >> output/knowledge/deps/run.log 2>&1
echo "$(date -u +%FT%T) deps done" >> output/knowledge/deps/run.log
