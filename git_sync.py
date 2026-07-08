"""Pushes local edits to tracked state files (config.json, verdicts.json,
scores.json) straight to GitHub, so hand-run commands like `verdict.py add`
and `watchlist.py add/remove` don't silently diverge from the repo that
GitHub Actions actually reads on every scheduled run. Without this, a locally
recorded verdict or watchlist change would sit invisible on the Mac until
someone remembered to `git add && commit && push` by hand.

Best-effort: failures print a clear manual-recovery instruction rather than
raising, so a git hiccup never blocks the CLI command that triggered it.
"""
import subprocess
import time
from pathlib import Path

REPO_DIR = Path(__file__).parent


def _run(args, **kw):
    return subprocess.run(["git", "-C", str(REPO_DIR)] + args,
                           capture_output=True, text=True, **kw)


def commit_and_push(paths, message):
    """Stage `paths` (relative to repo root), commit if changed, sync with
    the remote, and push. Prints a warning (never raises) on failure."""
    try:
        _run(["add", *paths])
        if _run(["diff", "--cached", "--quiet"]).returncode == 0:
            return  # nothing changed
        r = _run(["commit", "-m", message])
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip())

        # A scheduled GitHub Actions run can push at the same moment — retry
        # the pull/push cycle a few times before giving up, same as the
        # workflows' own retry loop.
        last_err = None
        for attempt in range(5):
            r = _run(["pull", "--rebase", "--autostash"])
            if r.returncode != 0:
                last_err = r.stderr.strip()
                time.sleep((attempt + 1) * 2)
                continue
            r = _run(["push"])
            if r.returncode == 0:
                print(f"  (synced to GitHub: {message})")
                return
            last_err = r.stderr.strip()
            time.sleep((attempt + 1) * 2)
        raise RuntimeError(last_err or "push failed after retries")
    except Exception as e:
        print(f"  WARNING: saved locally but git sync failed ({e}).\n"
              f"  GitHub Actions won't see this change until you push by hand:\n"
              f"    cd {REPO_DIR} && git add {' '.join(paths)} && "
              f"git commit -m 'manual sync' && git pull --rebase && git push")
