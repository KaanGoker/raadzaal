#!/usr/bin/env bash
# Stop a running pipeline runner and its current step, by pid. Never call pkill with a pattern from an interactive tool shell.
ps -eo pid,args | grep -E "[b]ash scripts/run_pipeline.sh|python -m [r]aadzaal (fetch|transcribe|diarise|align|speakers|summarise)" | awk '{print $1}' | while read -r p; do echo "stopping $p"; kill "$p"; done
