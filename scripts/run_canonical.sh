#!/usr/bin/env bash
# Detached canonical-source review (resumable: judged citations are skipped). Idle suspend inhibited while it runs.
#   start:  setsid nohup scripts/run_canonical.sh >/dev/null 2>&1 &
cd "$(dirname "$0")/.."
INHIBIT=()
command -v kde-inhibit >/dev/null && [ -n "$DBUS_SESSION_BUS_ADDRESS" ] && INHIBIT=(kde-inhibit --power)
"${INHIBIT[@]}" python3 scripts/canonicalize.py run >> output/mapping/canonical/run.log 2>&1
python3 scripts/map_questions.py post > output/mapping/post.log 2>&1
echo "$(date -u +%FT%T) canonical review + post-processing done" >> output/mapping/canonical/run.log
