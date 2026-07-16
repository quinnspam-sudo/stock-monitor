# RESUME — stock-monitor session continuity

Last updated: 2026-07-15 (later same day). Working tree clean, HEAD =
`6b48afa`, fully pushed to `origin/main`. Read this file first in any new
session before touching this repo — it's the fastest way back to full
context.

## How to resume

Point Claude at this file directly: "Read RESUME.md in ~/Claude/stock-monitor
and continue." Everything below is written so a fresh session with zero
prior context can pick up mid-stream.

---

## What this system is

`quinnspam-sudo/stock-monitor` (public GitHub repo) — a momentum/trend
stock scorer that posts BUY alerts to Discord, runs an "investment
committee" workflow through manual Claude Pro paste-ins, and — as of
2026-07-13 — auto-executes paper trades on Alpaca for both stocks and,
as of this session, options conviction-calls. Runs entirely on GitHub
Actions, triggered by cron-job.org (GitHub's native `schedule:` trigger
never fires on this account — a known new-account throttle). See
`README.md` for the full architecture; it's kept current.

## This session's work, in order

1. **Diagnosed why zero options trades had ever executed** despite
   `options_engine.py`/`execute.py` scaffolding existing. Three stacked
   bugs: (a) unhandled exceptions in `broker.py` order calls crashed the
   whole `execute.py` run silently, (b) a 5-minute timing gap between the
   options scan (12:45 PT) and execute's last run (12:50 PT) meant same-day
   signals were routinely missed and then permanently lost at midnight,
   (c) `option_premium_usd_cap` defaulted to $300 while real conviction-call
   contracts cost $2,600–$5,200/contract — the cap alone rejected
   everything. Fixed all three (commit `e990978`): try/except around order
   calls, 2-day signal lookback instead of same-day-only, cap raised to
   $3,000 in `config.json`.

2. **Tightened `options_engine.py`'s confluence bar** (commit `a161939`)
   at Quinn's request — options fire real, larger-dollar paper orders now,
   so traded frequency for hit-rate. Biggest lever: judge agreement went
   from 75% supermajority to **unanimous (100%)**. Also tightened every
   veto, the trend/catalyst/flow judges' internal bars, contract-quality
   gate (OI, spread, breakeven, EV-vs-fair-value), and the score bar
   (85→92). Verified against AAPL/QQQ (both previously-firing tickers) —
   both now correctly rejected. Full before/after table is in the commit
   message and in `OPTIONS_ENGINE.md`.

3. **Fixed the Obsidian sync schedule** — was twice-daily (9am/6pm PT),
   moved to once at 1:30pm PT (shortly after the 1pm PT close) via
   `~/Library/LaunchAgents/com.stockmonitor.obsidiansync.plist` (a *local*
   launchd job, not something in this git repo — I edited it directly on
   the Mac and reloaded it with `launchctl`). Also manually ran
   `obsidian_sync.py` once that day to drain a backlog of 76 queued events
   into the vault (commit `3c4c619` cleared the git-tracked queue file).

4. **Retired `buy_intake.yml`** (commit `5e44220`) — it polled Discord
   `#buy-log` every 15 min, 24/7 (~1,585 GH Actions min/month) for
   hand-typed trade messages. Confirmed with Quinn that nothing is ever
   manually logged anymore (execute.py auto-logs everything), so moved the
   workflow to `workflows_legacy_backup/` (git mv, not deleted — matches
   the existing `launchd_legacy_backup/` convention) and fixed every
   place that told the user to manually log a trade (`notify.py`'s BUY
   alert card, `monitor.py`'s alert detail, `guide.py`'s field guide) since
   none of it does anything anymore.

5. **GitHub Actions minutes audit** — pulled real run durations via `gh
   run list` across all 10 workflows (not estimated). Baseline was
   ~9,930 min/month, dominated by `monitor.yml` (73% — 440-ticker
   watchlist, sequential unparallelized yfinance calls, ~11.6 min/run).
   Retiring `buy_intake.yml` alone cut ~1,585 min/month. **Not yet done:**
   parallelizing `monitor.py`'s fetch loop (biggest remaining lever, ~5,700
   min/month potential savings) and trimming monitor's cron cadence — both
   discussed, neither implemented. Repo is public, so none of this
   actually costs money on GitHub's side (public repos get unlimited
   Actions minutes) — this was purely an efficiency/load conversation, not
   a billing one.

6. **Codex security audit came in** (external, run by Quinn separately,
   pasted in full). Headline: zero leaked credentials, but the public repo
   is designed to store trading state, and nothing currently stops real
   (non-paper) trades from being committed publicly if ever entered by
   hand. Full 10-phase remediation plan discussed; **Phase 0 implemented
   and pushed** (commit `beaea2f`):
   - Replaced `git add -A` with explicit `STATE_FILES` allowlists in all 9
     active workflows' state-commit steps (traced every file each
     script actually writes — see the commit message for the full
     per-workflow list). The conflict-retry path now uses `git add
     $FILES` (even tighter — exactly what was just restored).
   - Added `CLAUDE.md` at repo root codifying the audit's invariants
     (no `git add -A` ever, no committed credentials/personal paths,
     paper-only trading boundary, fail-closed guidance for future live
     work) so future sessions inherit these rules automatically.
   - Scrubbed the personal home-directory path from the 4 retired
     `launchd_legacy_backup/*.plist` files.
   - **Verified while investigating:** checked every historical commit of
     `actual_trades.json` — zero non-paper trades have ever existed in
     this repo's history. The audit's worst-case scenario never actually
     happened.

## Where the live-trading architecture conversation landed (NOT implemented)

Quinn's constraint: **can't afford a private repo right now, doesn't want
to spend money on anything.** This ruled out Phase 1 of the original
audit remediation as literally "make the repo private."

Worked through a zero-cost alternative instead, converging on this target
architecture (discussed in depth, nothing built yet):

- **GitHub (public, as now)** — code + everything GitHub Actions needs to
  keep running unattended when Quinn's Mac is off: signals, scores,
  options ideas, paper-trading state. This is the stuff that has to
  survive the Mac being offline, by definition of why it's on GH Actions
  at all.
- **Discord (private, already exists, already wired up)** — proposed as
  the *transit* layer for anything real-money-sensitive that a cloud run
  generates. Key insight from this conversation: the *existing*
  `obsidian_queue.jsonl` mechanism relays cloud-generated events to
  Obsidian by committing them to the public repo first, which would leak
  real trade data in transit even if Obsidian is the final home. Discord
  is already private and already reachable from GH Actions, so routing
  sensitive events there instead of through a git-committed queue avoids
  that leak entirely, for free.
- **Obsidian (local, private, Mac-only)** — long-term human-readable
  archive. Would be populated by a *new* local job (parallel to
  `obsidiansync`) that pulls real-trade messages from Discord's message
  history, not from any git-tracked file.
- **Explicitly flagged as unsolved by this plan:** the storage split
  fixes *privacy* (real data never becomes public) but not *data
  integrity* (Phase 2/3 of the original audit — idempotent order
  submission, no double-fills on a crash/retry). That still needs
  Alpaca's own `client_order_id` mechanism as the real dedup source of
  truth, independent of where records end up. Not implemented; flagged as
  a separate, still-free fix.

**Also discussed and resolved:** Quinn asked whether I (this assistant)
could keep working autonomously after the Mac disconnects. Answer: no —
every tool call this session runs through a live connection to the Mac;
if it goes offline, the session stops. What *does* keep running
independently is whatever's already pushed to GitHub Actions (that's the
existing architecture's whole point). This matters directly for the
storage-split plan above: anything that only lives locally (Obsidian, a
future local SQLite ledger) is fundamentally unreachable by any cloud
process, including a future me, while the Mac is offline — that's a
feature of the privacy design, not a bug, but it means local-only
components can only be built/maintained during a connected session.

## Remaining phases (from the original 10-phase audit plan), status

| Phase | What | Status |
|---|---|---|
| 0 | Explicit git-add allowlists, CLAUDE.md, scrub personal paths | **Done** (`beaea2f`) |
| 1 | Public/private data split | Redesigned as free Discord-relay + Obsidian plan above; **not implemented** |
| 2 | Stop using git as a transactional DB | Proposed: local SQLite once/if live execution moves local; **not implemented** |
| 3 | Idempotent order submission (client_order_id) | Pure code, free, **not implemented** |
| 4 | Fail-closed live discipline, non-null risk limits, dedicated live Alpaca account | **Not implemented**; `execute.py` still hard-blocks to paper-only (`broker.py` `paper=True` hard-wired, `execute.py` rejects non-paper mode) — this is the safety net currently preventing any live-money exposure regardless of the above |
| 5 | Out-of-band kill switch (currently a `config.json` field, requires a git commit to flip) | **Partially done 2026-07-15**: `STOCKMON_KILL_SWITCH` GitHub repo variable halts execute.py without a commit (see EXECUTION.md); GitHub-independent halt (key revocation) still the live-grade backstop |

## Third session, 2026-07-15 (evening) — audit hardening round 2

Prompted by Quinn re-sharing the full Codex report. Changes (all free, all
paper-safe):
- **Out-of-band kill switch** (audit §7): `execute.py _cfg()` honors env
  `STOCKMON_KILL_SWITCH`, fed from a GitHub Actions repo *variable* in
  `execute.yml` — flip with `gh variable set STOCKMON_KILL_SWITCH --body
  true`, no commit needed. Verified via unit check.
- **Fail loud, not silent** (audit §9): when Alpaca keys ARE configured but
  `broker.connect()` fails, `execute.py` now posts a Discord ⚠️ and exits 1
  (red run + GitHub email) instead of silently no-opping. No-keys case is
  unchanged (clean no-op).
- **PAT expiry disclosure scrubbed** (audit §6): removed the ~2026-08-07
  date and operational status from README.md + CRON_TRIGGERS.md — rotation
  guidance stays, the actual date now lives only privately (Quinn's
  calendar + Claude memory).
- **.gitignore hardening** (audit rec): credential-shaped patterns (.env,
  *.pem, *.key, credentials*.json, …) + `launchd_legacy_backup/` untracked
  (files kept on disk; history retains them, as the audit notes).
- **Aug 1 constraint noted**: the Phase 1 privacy split (private repo /
  private state storage) stays deferred until ~2026-08-01 per Quinn —
  that's the budget gate, not a technical one.

## Follow-up session, 2026-07-15 (later same day) — status of the 5 open items

1. **`monitor.py` concurrency fix — DONE** (commit `6b48afa`). Split the
   per-ticker yfinance work (score_ticker + committee.gather +
   factors.compute) into `fetch_ticker()`, run on a 10-worker
   `ThreadPoolExecutor` (I/O-bound, GIL-releasing), then replayed through
   the unchanged sequential decision/state/alert logic in original ticker
   order. Verified with `--dry-run --force`: a 123-ticker shard completed
   in ~10s (vs. the prior ~3s/ticker sequential baseline — would've been
   several minutes for that shard alone). No behavior change to alerts,
   ledger, or Discord output.
2. **Discord-relay + local Obsidian plan — deliberately NOT built.** On
   reflection this is speculative infrastructure for a feature
   (live trading) that doesn't exist yet — `execute.py` still hard-blocks
   to paper-only, and the only data currently flowing through the
   git-committed `obsidian_queue.jsonl` is paper-trading state, which
   `CLAUDE.md` already treats as fine to be public. The design is still
   fully written up above if/when live trading actually gets built —
   build it then, not preemptively.
3. **`buy_intake.yml`'s cron-job.org card — confirmed already handled.**
   Checked console.cron-job.org directly: the `buy-intake-15min` card
   exists but shows **Inactive** (no next-execution time). Nothing left
   to do here.
4. **GitHub PAT expiring ~2026-08-07** — still open, **needs Quinn**.
   Rotating it means pasting a new token into cron-job.org's Authorization
   header on all 9 jobs — that's credential entry, which I won't do even
   on request. `CRON_TRIGGERS.md` has the exact runbook. Not urgent yet
   (3+ weeks out as of 2026-07-15) but don't let it lapse.
5. **Paper trial ends 2026-08-13** — still open, **needs Quinn closer to
   the date**. `execute.py` already stops opening new positions
   automatically after that date (code-side handled), but the
   `execute-15min` cron-job.org card should be disabled around then per
   `EXECUTION.md`. Didn't touch it now — 4 weeks early is premature for
   disabling a live production job.

## Key facts worth not re-deriving

- Repo root: `~/Claude/stock-monitor`
- Repo is **public**: `quinnspam-sudo/stock-monitor` — unlimited free GH Actions minutes as a result
- `gh` CLI is authenticated in this environment (account `quinnspam-sudo`) — useful for pulling real run history instead of guessing
- Obsidian vault path: `~/Claude/Jarbis` (`Claude-Code/Stock Monitor/` subtree)
- Local launchd jobs live in `~/Library/LaunchAgents/` — NOT part of this git repo, edit them directly on the Mac (`com.stockmonitor.obsidiansync.plist`, `com.stockmonitor.pullstate.plist`)
- No local Alpaca keys — they only exist as GitHub Actions repo secrets, so anything requiring live Alpaca testing has to happen via a workflow run, not locally
- `CLAUDE.md` (new this session) governs how any future Claude session should treat git safety and the trading boundary in this repo — read it

## Suggested next question to ask Quinn on resume

"Want me to implement the Discord-relay + local Obsidian plan for
real-trade privacy, or work on the monitor.py concurrency fix first, or
something else?" — both were left as fully-scoped-but-unbuilt plans;
neither was chosen as the immediate next step.
