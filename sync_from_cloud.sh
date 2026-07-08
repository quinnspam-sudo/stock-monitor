#!/bin/bash
# Pulls state committed by GitHub Actions, replays any queued Obsidian events
# into the real Jarbis vault, then pushes the cleared queue back so it
# doesn't get replayed twice. Best-effort: never fails loudly (launchd job).
set -e
cd "$(dirname "$0")"

git pull --rebase --autostash -q
./venv/bin/python obsidian_sync.py

[ -f obsidian_queue.jsonl ] && git add obsidian_queue.jsonl
if ! git diff --cached --quiet; then
    git commit -q -m "sync: clear replayed obsidian queue [skip ci]"
    git pull --rebase --autostash -q
    git push -q
fi
