"""Replays Obsidian events queued by GitHub Actions runs (which have no
access to the local Jarbis vault) into the real vault.

Run periodically on the Mac — e.g. via a launchd job on login/wake, or by
hand: ./venv/bin/python obsidian_sync.py

Expects the repo to already be pulled (a wrapper script/launchd job should
`git pull` first, then run this, then commit+push the cleared queue file).
"""
import json
from datetime import datetime
from pathlib import Path

import obsidian
from obsidian import PACIFIC

QUEUE_PATH = Path(__file__).parent / "obsidian_queue.jsonl"


def main():
    if not QUEUE_PATH.exists() or not QUEUE_PATH.read_text().strip():
        print("No queued events.")
        return

    lines = [l for l in QUEUE_PATH.read_text().splitlines() if l.strip()]
    replayed = 0
    for line in lines:
        event = json.loads(line)
        try:
            if event["type"] == "ping":
                when = datetime.strptime(event["ts"], "%Y-%m-%d %H:%M").replace(tzinfo=PACIFIC) \
                    if event.get("ts") else None
                obsidian.log_ping(event["kind"], event["text"], when=when)
            elif event["type"] == "mirror_payload":
                p = Path(__file__).parent / event["path"]
                if p.exists():
                    obsidian.mirror_payload(p)
                else:
                    print(f"  skip (payload file missing): {event['path']}")
            replayed += 1
        except Exception as e:
            print(f"  skip (error replaying {event}): {e}")

    QUEUE_PATH.write_text("")
    print(f"Replayed {replayed}/{len(lines)} queued event(s) into the vault.")


if __name__ == "__main__":
    main()
