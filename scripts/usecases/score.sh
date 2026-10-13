#!/bin/sh
# Scores use-case answers in a throwaway container, because score.py runs
# model-written code: no network, read-only filesystem, 64 MB /tmp, 512 MB RAM,
# 128 processes, no capabilities, unprivileged user. Run it from the repo root;
# paths are relative to it.
#   sh scripts/usecases/score.sh --selftest scripts/usecases/tasks.json
#   sh scripts/usecases/score.sh --cases scripts/usecases/tasks.json scripts/usecases/scorer-cases.json
#   sh scripts/usecases/score.sh scripts/usecases/tasks.json my-run.jsonl > my-scores.jsonl
exec docker run --rm --network none --read-only --tmpfs /tmp:rw,size=64m,mode=1777 \
  --memory 512m --cpus 2 --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges \
  --user 65534:65534 -v "$PWD:/w:ro" -w /w python:3.13-slim python3 scripts/usecases/score.py "$@"
