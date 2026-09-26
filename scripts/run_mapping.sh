#!/usr/bin/env bash
# Detached full mapping run: survives the Claude session; safe to kill and restart (finished questions are skipped).
#   start:  setsid nohup scripts/run_mapping.sh >/dev/null 2>&1 &
#   stop:   touch output/mapping/STOP   (graceful)   or   kill $(cat output/mapping/run_direct.pid)
# While it runs, KDE idle auto-suspend is inhibited (kde-inhibit --power); closing the lid still suspends.
cd "$(dirname "$0")/.."
INHIBIT=()
command -v kde-inhibit >/dev/null && [ -n "$DBUS_SESSION_BUS_ADDRESS" ] && INHIBIT=(kde-inhibit --power)
"${INHIBIT[@]}" python3 scripts/map_direct.py run GS LA >> output/mapping/run_direct.log 2>&1
python3 scripts/map_questions.py post > output/mapping/post.log 2>&1
echo "$(date -u +%FT%T) post-processing done" >> output/mapping/run_direct.log
