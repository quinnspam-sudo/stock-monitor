#!/bin/bash
# Fast-pull job: keeps local dashboard.html / ecosystem.html / state files in
# step with the GitHub Actions pipeline (which commits every monitor run).
# Deliberately does NOT replay the Obsidian queue — sync_from_cloud.sh owns
# that on its twice-daily schedule.
cd "$(dirname "$0")"
git pull --rebase --autostash -q
