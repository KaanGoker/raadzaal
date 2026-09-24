#!/usr/bin/env bash
# Run the GPU and LLM steps for every session that needs them, one after the other, resumable.
# usage: nohup bash scripts/run_pipeline.sh > data/pipeline.log 2>&1 &
set -u
cd "$(dirname "$0")/.."
source scripts/cuda_env.sh
export PYTHONUNBUFFERED=1
for step in ${STEPS:-agenda fetch transcribe diarise regroup align speakers summarise names}; do
  echo "== $step $(date -u +%FT%TZ)"
  ./venv/bin/python -m raadzaal "$step" "$@"
done
./venv/bin/python -m raadzaal build
./venv/bin/python -m raadzaal report
./venv/bin/python -m raadzaal status
