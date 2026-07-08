# stock-monitor

Watchlist monitor that scores stocks on momentum/trend signals and posts BUY alerts
to a private Discord server via webhook. Recommends only — never trades.

## Setup (one time)

1. Create a private Discord server (or use an existing one) and a channel like `#buy-alerts`.
2. In Discord: **Server Settings → Integrations → Webhooks → New Webhook** →
   pick the channel → **Copy Webhook URL**.
3. Paste that URL into `secrets.json` (create it if missing) as `discord_webhook_url`:
   ```json
   {"discord_webhook_url": "https://discord.com/api/webhooks/..."}
   ```
   `secrets.json` is gitignored — the webhook never lands in version control or an
   `ultrareview`/`git init` of this folder. (You can also set the `DISCORD_WEBHOOK_URL`
   env var instead, which takes priority.)
4. Test it: `./venv/bin/python notify.py` — you should see a message in the channel.

## Usage

```bash
./venv/bin/python monitor.py            # score watchlist, send alerts for scores >= threshold
./venv/bin/python monitor.py --dry-run  # score only, no Discord messages
```

## Config (`config.json`)

- `watchlist` — tickers to monitor
- `alert_threshold` — score (0–100) required to trigger a BUY alert (default 75)
- `cooldown_hours` — suppress repeat alerts for the same ticker (default 24)
- `obsidian_vault` — path to the Obsidian vault to mirror payloads into

Secrets (`discord_webhook_url`) live in `secrets.json`, not `config.json` — see Setup above.

## Scheduled jobs (launchd LaunchAgents, Pacific time)

Jobs run via `~/Library/LaunchAgents/com.stockmonitor.*.plist` (not cron):
launchd fires missed jobs when the Mac wakes, so closing the lid no longer
silently kills a day of monitoring. Caveat: nothing runs while asleep — a
catch-up fires on wake. For true market-hours coverage, keep the Mac plugged
in with lid open or enable a scheduled wake (`sudo pmset repeat wakeorpoweron
MTWRF 05:25:00`).

## Legacy schedule reference (same times, now in launchd)

- `monitor.py` — every 15 min, 6:00–12:45 PT Mon–Fri: scores, delta triggers, Template A payloads
- `pulse.py` — hourly 7:00–12:00 PT (10 AM–3 PM ET): Template C intraday pulse payload
- `close.py` — 13:35 PT (post 4:30 ET bell): Template D closing bell payload
- `ipo.py` — 5:30 AM PT daily: EDGAR scan for S-1/S-1A/424B4 filings → Template B triage payload (incl. sector concentration)
- `weekly.py` — Friday 13:45 PT: weekly performance review payload (verdicts vs SPY)
- `backtest.py` — Saturday 09:00 PT: backtests the *local scoring engine's* calls
  (not committee verdicts — that's `weekly.py`) against what each ticker actually
  did over the Mon–Fri just finished, using `history.json` snapshots

All jobs skip market holidays automatically (`--force` overrides). Output appends
to `monitor.log` (auto-rotated at ~1 MB). Edit schedule with `crontab -e`.

## Obsidian integration

All pings are offloaded to the Jarbis vault (`obsidian_vault` in config.json)
under `Claude-Code/Stock Monitor/`:

- `Pings/YYYY-MM-DD.md` — every alert/notice appended to a daily note
- `Weeks/YYYY-Www.md` — rollup of that ISO week's day notes, plus any weekly
  review/backtest payloads dated within it
- `Months/YYYY-MM.md` — rollup of that month's week notes
- `Committee Payloads/` — every payload mirrored with frontmatter
  (`status: awaiting-verdict`) so you can paste into Claude Pro from Obsidian.
  Recording a verdict (`verdict.py add`) flips the status to `verdict-recorded`
  and appends the rating/entry/note directly onto the payload note.
- `Tickers/TICKER.md` — per-ticker rollup: every committee payload and recorded
  verdict for that name in one note, so you can browse "everything ever said
  about NVDA" instead of hunting through daily pings. Regenerated automatically
  whenever a new payload is mirrored or a verdict is recorded.
- `Stock Monitor Hub.md` — index note; links to the current day/week/month note

Every day note links up to its week note, which links up to its month note,
which links up to the Hub — the vault is browsable day-by-day, week-by-week, or
month-by-month, not just as a flat pile of daily files. All three levels
(day/week/month) regenerate automatically on every ping, so they never drift.

Vault writes are best-effort: Obsidian problems never break monitoring.

## Dashboard

Every monitor run regenerates `dashboard.html` (ranked scoreboard with ratings,
intraday deltas, earnings proximity, sectors). Open it once and leave it up:

```bash
open ~/Claude/stock-monitor/dashboard.html   # auto-refreshes every 5 min
```

## Watchlist management

```bash
./venv/bin/python watchlist.py list          # tickers with current scores/ratings
./venv/bin/python watchlist.py add PLTR      # validates ticker before adding
./venv/bin/python watchlist.py remove TSLA   # also clears its ledger entry
```

## Discord field guide

`./venv/bin/python guide.py` posts the alert field guide (every output type,
meaning, and call to action) to Discord — re-run after changing any output
format, and keep it pinned in the channel.

## Verdict journal (closing the loop)

After pasting a payload into Claude Pro and getting a committee verdict, record it:

```bash
./venv/bin/python verdict.py add AAPL "Buy" --entry 308 --note "margin expansion thesis"
./venv/bin/python verdict.py review   # performance of every verdict vs price since
```

## Weekly backtest (accuracy check)

Every Saturday, `backtest.py` grabs the first rating each ticker got during the
week just finished (from `history.json`) and checks it against that ticker's
actual return over the same week:

```bash
./venv/bin/python backtest.py --force   # run manually any day (skips the Saturday check)
```

Reports, per rating bucket (Buy/Strong Buy, Watch/Hold, Reduce/Sell): average
return, hit rate, and win rate vs SPY — plus whether top-half-scored tickers
actually beat bottom-half-scored ones that week (the core "does the scoring
signal mean anything" check). Output is a payload in `committee_prompts/`
(mirrored to Obsidian like other payloads) and a running history in
`backtest_log.json` so accuracy trends are visible over time, not just
week-to-week.

## Files

- `config.json` — watchlist, thresholds, Discord webhook
- `scores.json` — ledger of last proxy scores per ticker (delta baseline)
- `history.json` — intraday score history, last 30 days (feeds close.py)
- `verdicts.json` — committee verdict journal
- `backtest_log.json` — weekly scoring-accuracy history (from `backtest.py`)
- `committee_prompts/` — generated payloads for Claude Pro (auto-pruned after 14 days)
- `alert_state.json` — Discord alert cooldowns

## Committee pipeline (manual Claude Pro workflow)

Each run, [committee.py](committee.py) computes proxy scores for all 11 categories
(/110) plus timing and confidence from yfinance data, and diffs them against the
`scores.json` ledger. Only when a Phase 3 threshold is breached (overall Δ≥8,
timing Δ≥15, confidence Δ≥10pp, or first evaluation) does it write a consolidated
payload to `committee_prompts/` and ping Discord that payloads are ready. Paste
the payload file into your Claude Pro committee session to get the Template output.
Data yfinance can't provide (congressional trades, options skew, etc.) is marked
`Data Status: GAPPED` in every payload.

## Scoring

Current score is momentum/trend only (price vs 50-day SMA, 1/3-month returns,
proximity to 3-month high, RSI, volume confirmation) — a placeholder to expand
with fundamentals, earnings revisions, insider buying, etc. per the larger system design.
